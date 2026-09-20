import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from asr_backend import crud, models, schemas, screening
from asr_backend.citation_import import ParsedCitation

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class ChoicesMismatchError(ValueError):
    """Raised when resolution choices don't cover exactly a Possible Duplicate's conflicts."""


@dataclass(frozen=True)
class FieldConflict:
    field: schemas.ConflictFieldName
    extraction_field_id: uuid.UUID | None = None


def normalize_title(title: str) -> str:
    return _NON_ALNUM.sub("", title.lower())


def is_match(a: models.Citation, b: models.Citation) -> bool:
    """Whether two Citations are a Duplicate match, per ADR 0005: exact-only.

    DOI takes precedence when both sides have one, even if titles differ;
    otherwise falls back to normalized title.
    """
    if a.doi and b.doi:
        return a.doi == b.doi
    return normalize_title(a.title) == normalize_title(b.title)


def find_conflicts(a: models.Citation, b: models.Citation) -> list[FieldConflict]:
    """Every field on which a matched pair already carries conflicting Reviewer-entered data.

    Checked field-by-field (Screening Decision, Full-Text Decision, each
    Extraction Field, Full Text) rather than citation-wide, so a Reviewer
    resolving a Possible Duplicate can pick a winner per conflicting field
    instead of for the pair as a whole.
    """
    conflicts: list[FieldConflict] = []
    if (
        a.owner_screening_decision is not None
        and b.owner_screening_decision is not None
        and a.owner_screening_decision.decision != b.owner_screening_decision.decision
    ):
        conflicts.append(FieldConflict(field="screening_decision"))
    if (
        a.full_text_decision is not None
        and b.full_text_decision is not None
        and a.full_text_decision.decision != b.full_text_decision.decision
    ):
        conflicts.append(FieldConflict(field="full_text_decision"))
    if a.full_text is not None and b.full_text is not None:
        conflicts.append(FieldConflict(field="full_text"))
    a_values = {value.extraction_field_id: value.value for value in a.extraction_values}
    b_values = {value.extraction_field_id: value.value for value in b.extraction_values}
    for field_id, value in a_values.items():
        if field_id in b_values and b_values[field_id] != value:
            conflicts.append(FieldConflict(field="extraction_value", extraction_field_id=field_id))
    return conflicts


def find_match(
    citation: models.Citation, pool: list[models.Citation]
) -> models.Citation | None:
    for candidate in pool:
        if is_match(citation, candidate):
            return candidate
    return None


class MatchIndex:
    """Finds the earliest Citation that `is_match` would pick, without scanning them all.

    Holds only ids and match keys (DOI, normalized title), never ORM objects:
    every commit expires whatever the Session still holds strongly, so a pool
    of live Citation rows would cost O(pool) per commit and force a refresh
    query per row on the next read.

    Add Citations in creation order — the earliest-added match wins, mirroring
    `find_match` over a created_at-ordered pool. Mirrors `is_match`: two DOIs
    compare on DOI alone (titles are ignored); otherwise normalized titles are
    compared, so a DOI-bearing Citation can match a DOI-less one on title but
    never a different-DOI one.
    """

    def __init__(self, citations: Iterable[models.Citation] = ()) -> None:
        self._entries: dict[uuid.UUID, tuple[int, str | None, str]] = {}
        self._by_doi: dict[str, dict[uuid.UUID, int]] = {}
        self._by_title: dict[str, dict[uuid.UUID, int]] = {}
        self._by_title_without_doi: dict[str, dict[uuid.UUID, int]] = {}
        self._next_position = 0
        for citation in citations:
            self.add(citation)

    def add(self, citation: models.Citation) -> None:
        self.remove(citation.id)
        position = self._next_position
        self._next_position += 1
        doi = citation.doi or None
        title = normalize_title(citation.title)
        self._entries[citation.id] = (position, doi, title)
        self._by_title.setdefault(title, {})[citation.id] = position
        if doi is None:
            self._by_title_without_doi.setdefault(title, {})[citation.id] = position
        else:
            self._by_doi.setdefault(doi, {})[citation.id] = position

    def remove(self, citation_id: uuid.UUID) -> None:
        entry = self._entries.pop(citation_id, None)
        if entry is None:
            return
        _, doi, title = entry
        self._by_title[title].pop(citation_id, None)
        if doi is None:
            self._by_title_without_doi[title].pop(citation_id, None)
        else:
            self._by_doi[doi].pop(citation_id, None)

    def find_match(self, citation: models.Citation) -> uuid.UUID | None:
        """The earliest indexed Citation (other than `citation` itself) that matches it."""
        doi = citation.doi or None
        title = normalize_title(citation.title)
        if doi is None:
            candidates = [self._by_title.get(title, {})]
        else:
            candidates = [self._by_doi.get(doi, {}), self._by_title_without_doi.get(title, {})]
        best_id, best_position = None, None
        for group in candidates:
            for candidate_id, position in group.items():
                if candidate_id == citation.id:
                    continue
                if best_position is None or position < best_position:
                    best_id, best_position = candidate_id, position
                break
        return best_id


def _combine_bibliographic_fields(survivor: models.Citation, loser: models.Citation) -> None:
    if survivor.abstract is None and loser.abstract is not None:
        survivor.abstract = loser.abstract
    if not survivor.authors and loser.authors:
        survivor.authors = loser.authors
    if survivor.year is None and loser.year is not None:
        survivor.year = loser.year
    merged_sources = list(survivor.source)
    for source in loser.source:
        if source not in merged_sources:
            merged_sources.append(source)
    survivor.source = merged_sources


def _copy_field(
    db: Session,
    project: models.ReviewProject,
    survivor: models.Citation,
    loser: models.Citation,
    field: schemas.ConflictFieldName,
    extraction_field_id: uuid.UUID | None = None,
) -> None:
    """Copies the loser's value for one Reviewer-entered field onto the survivor.

    Shared by Duplicate merge (looped once per field the survivor is missing)
    and Possible Duplicate resolution (called once per Reviewer-picked field),
    so a fix to how one field is copied can't land in one path without the
    other.
    """
    if field == "screening_decision":
        crud.upsert_screening_decision(
            db,
            project,
            survivor.id,
            project.owner_reviewer_id,
            schemas.ScreeningDecisionCreate(
                decision=loser.owner_screening_decision.decision,
                reason=loser.owner_screening_decision.reason,
            ),
        )
    elif field == "full_text":
        crud.upsert_full_text(
            db,
            survivor.id,
            original_filename=loser.full_text.original_filename,
            file_path=loser.full_text.file_path,
            parsed_text=loser.full_text.parsed_text,
            parse_status=loser.full_text.parse_status,
        )
    elif field == "full_text_decision":
        crud.upsert_full_text_decision(
            db,
            survivor.id,
            schemas.FullTextDecisionCreate(
                decision=loser.full_text_decision.decision,
                reason=loser.full_text_decision.reason,
            ),
        )
    elif field == "extraction_value":
        crud.upsert_extraction_value(
            db,
            survivor.id,
            extraction_field_id,
            schemas.ExtractionValueCreate(value=loser.extraction_value_for(extraction_field_id)),
        )


def _transfer_reviewer_data(
    db: Session, project: models.ReviewProject, survivor: models.Citation, loser: models.Citation
) -> None:
    """Copies Reviewer-entered data the loser has and the survivor lacks.

    Always a copy onto a new row keyed to the survivor, never a reassignment
    of the loser's own row, so the archived Citation keeps its original data.
    """
    if survivor.owner_screening_decision is None and loser.owner_screening_decision is not None:
        _copy_field(db, project, survivor, loser, "screening_decision")
    if survivor.full_text is None and loser.full_text is not None:
        _copy_field(db, project, survivor, loser, "full_text")
    if survivor.full_text_decision is None and loser.full_text_decision is not None:
        _copy_field(db, project, survivor, loser, "full_text_decision")
    survivor_field_ids = {value.extraction_field_id for value in survivor.extraction_values}
    for value in loser.extraction_values:
        if value.extraction_field_id not in survivor_field_ids:
            _copy_field(db, project, survivor, loser, "extraction_value", value.extraction_field_id)


def merge_pair(
    db: Session,
    project: models.ReviewProject,
    survivor: models.Citation,
    loser: models.Citation,
) -> None:
    """Merges loser into survivor per the project's Merge Mode, then archives loser."""
    if project.merge_mode == "combine":
        _combine_bibliographic_fields(survivor, loser)
    _transfer_reviewer_data(db, project, survivor, loser)
    loser.archived = True
    loser.merged_into_citation_id = survivor.id
    db.commit()


def _build_match_index(db: Session, project: models.ReviewProject) -> MatchIndex:
    """Indexes the Review Project's active Citations, minus any held in a Possible Duplicate.

    A held Citation is excluded from matching so a later upload can't
    auto-merge it away out from under the pending hold (ticket #21).
    """
    held = crud.held_citation_ids(db, project.id)
    return MatchIndex(c for c in crud.list_citations(db, project.id) if c.id not in held)


def _match_and_merge(
    db: Session, project: models.ReviewProject, index: MatchIndex, citation: models.Citation
) -> bool:
    """Matches one Citation against the index; merges or holds it, keeping the index current.

    Returns whether it matched anything. On a merge the loser is archived, and
    on a hold both sides are excluded from later matching — the same pool
    `crud.list_citations` minus `crud.held_citation_ids` would yield next time.
    """
    match_id = index.find_match(citation)
    if match_id is None:
        return False
    match = db.get(models.Citation, match_id)
    conflicts = find_conflicts(match, citation)
    if conflicts:
        crud.create_possible_duplicate(db, project.id, survivor_id=match.id, loser_id=citation.id)
        index.remove(match.id)
    else:
        merge_pair(db, project, survivor=match, loser=citation)
    index.remove(citation.id)
    return True


def process_upload_matches(
    db: Session, project: models.ReviewProject, new_citations: list[models.Citation]
) -> None:
    """Runs Duplicate matching for already-persisted Citations.

    A non-conflicting match merges immediately; a conflicting one is held as
    a Possible Duplicate for manual resolution instead (ticket #21) rather
    than silently left unmerged.

    Each given Citation is checked against the Review Project's other
    currently-active Citations, excluding any Citation that is already one
    side of an unresolved Possible Duplicate — otherwise this upload could
    auto-merge that Citation away out from under the pending hold. The
    earlier-created side of any match always survives — which holds true
    here only because the caller guarantees each given Citation was already
    active in the database before any Citation created after it was.
    Bulk-persisting a whole batch and then calling this once over all of it
    would violate that guarantee, since two same-batch rows would each see
    the other as already active; import_citations avoids that by creating
    and matching one row at a time.
    """
    index = _build_match_index(db, project)
    for citation in new_citations:
        _match_and_merge(db, project, index, citation)


def _apply_resolution_choice(
    db: Session,
    project: models.ReviewProject,
    survivor: models.Citation,
    loser: models.Citation,
    choice: schemas.ConflictResolutionChoice,
) -> None:
    """Copies the loser's value for one conflicting field onto the survivor.

    A no-op when the survivor's own value is the chosen winner, since it's
    already in place.
    """
    if choice.winner == "survivor":
        return
    _copy_field(db, project, survivor, loser, choice.field, choice.extraction_field_id)


def _validate_choices_match_conflicts(
    conflicts: list[FieldConflict], choices: list[schemas.ConflictResolutionChoice]
) -> None:
    conflict_keys = {(conflict.field, conflict.extraction_field_id) for conflict in conflicts}
    choice_keys = {(choice.field, choice.extraction_field_id) for choice in choices}
    if conflict_keys != choice_keys:
        raise ChoicesMismatchError(
            "Resolution choices must cover exactly the Possible Duplicate's conflicting fields"
        )


def resolve_possible_duplicate(
    db: Session,
    project: models.ReviewProject,
    possible_duplicate: models.PossibleDuplicate,
    choices: list[schemas.ConflictResolutionChoice],
) -> models.Citation:
    """Applies the Reviewer's picked values, then merges the pair as an automatic match would.

    The survivor is always `possible_duplicate.survivor_citation` — the
    earlier-created side fixed at creation time — so a Reviewer's choices
    only ever supply the correct value for the disputed field(s), never
    nominate the other Citation as the survivor instead.
    """
    survivor = possible_duplicate.survivor_citation
    loser = possible_duplicate.loser_citation

    conflicts = find_conflicts(survivor, loser)
    _validate_choices_match_conflicts(conflicts, choices)

    for choice in choices:
        _apply_resolution_choice(db, project, survivor, loser, choice)

    merge_pair(db, project, survivor=survivor, loser=loser)
    crud.set_possible_duplicate_status(db, possible_duplicate, "resolved")
    return survivor


def _conflict_field_read(
    conflict: FieldConflict, extraction_fields_by_id: dict[uuid.UUID, models.ExtractionField]
) -> schemas.ConflictFieldRead:
    extraction_field_name = None
    if conflict.extraction_field_id is not None:
        field = extraction_fields_by_id.get(conflict.extraction_field_id)
        extraction_field_name = field.name if field is not None else None
    return schemas.ConflictFieldRead(
        field=conflict.field,
        extraction_field_id=conflict.extraction_field_id,
        extraction_field_name=extraction_field_name,
    )


def _citation_read_for(
    citation: models.Citation, viewer: models.Reviewer
) -> schemas.PossibleDuplicateCitationRead:
    """The Citation as `viewer` may see it: in a Dual project, with the screening
    decision withheld unless the viewer has decided this Citation themselves
    (ADR 0006, #54). That field carries the Owner's decision, so it is the peer's
    for a Co-Reviewer."""
    read = schemas.PossibleDuplicateCitationRead.model_validate(citation)
    if screening.is_blind(citation.review_project, citation.screening_decision_for(viewer.id)):
        read.screening_decision = None
    return read


def to_possible_duplicate_read(
    possible_duplicate: models.PossibleDuplicate, viewer: models.Reviewer
) -> schemas.PossibleDuplicateRead:
    survivor = possible_duplicate.survivor_citation
    loser = possible_duplicate.loser_citation
    conflicts = find_conflicts(survivor, loser)
    extraction_fields_by_id = {
        field.id: field for field in survivor.review_project.extraction_fields
    }
    return schemas.PossibleDuplicateRead(
        id=possible_duplicate.id,
        survivor=_citation_read_for(survivor, viewer),
        loser=_citation_read_for(loser, viewer),
        conflicting_fields=[_conflict_field_read(c, extraction_fields_by_id) for c in conflicts],
        created_at=possible_duplicate.created_at,
    )


def import_citations(
    db: Session, project: models.ReviewProject, parsed_citations: list[ParsedCitation]
) -> list[uuid.UUID]:
    """Creates each parsed Citation and runs Duplicate matching against it in turn.

    Returns the created Citations' ids (including any merged away or held
    straight afterwards). Ids rather than ORM rows, because every commit
    expires each row the Session still holds: returning the rows keeps all n
    alive and makes each of the n commits cost O(n).

    Rows are created and matched one at a time, not bulk-created up front, so
    that an earlier row in the same batch is always already active by the
    time a later, matching row is checked against it (see process_upload_matches).
    The match index is built once from the Citations already in the database
    and then extended row by row, rather than re-queried per row (O(n^2) rows
    read for an n-row upload). It is a snapshot: Citations another request adds
    to this Review Project mid-import aren't matched against.
    """
    index = _build_match_index(db, project)
    created_ids = []
    for parsed in parsed_citations:
        [citation] = crud.create_citations(db, project.id, [parsed])
        created_ids.append(citation.id)
        if not _match_and_merge(db, project, index, citation):
            index.add(citation)
    return created_ids
