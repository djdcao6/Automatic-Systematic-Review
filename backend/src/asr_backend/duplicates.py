import re
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from asr_backend import crud, models, schemas
from asr_backend.citation_import import ParsedCitation

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class ChoicesMismatchError(ValueError):
    """Raised when resolution choices don't cover exactly a Possible Duplicate's conflicts."""


@dataclass(frozen=True)
class Conflict:
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


def find_conflicts(a: models.Citation, b: models.Citation) -> list[Conflict]:
    """Every field on which a matched pair already carries conflicting Reviewer-entered data.

    Checked field-by-field (Screening Decision, Full-Text Decision, each
    Extraction Field, Full Text) rather than citation-wide, so a Reviewer
    resolving a Possible Duplicate can pick a winner per conflicting field
    instead of for the pair as a whole.
    """
    conflicts: list[Conflict] = []
    if (
        a.screening_decision is not None
        and b.screening_decision is not None
        and a.screening_decision.decision != b.screening_decision.decision
    ):
        conflicts.append(Conflict(field="screening_decision"))
    if (
        a.full_text_decision is not None
        and b.full_text_decision is not None
        and a.full_text_decision.decision != b.full_text_decision.decision
    ):
        conflicts.append(Conflict(field="full_text_decision"))
    if a.full_text is not None and b.full_text is not None:
        conflicts.append(Conflict(field="full_text"))
    a_values = {value.extraction_field_id: value.value for value in a.extraction_values}
    b_values = {value.extraction_field_id: value.value for value in b.extraction_values}
    for field_id, value in a_values.items():
        if field_id in b_values and b_values[field_id] != value:
            conflicts.append(Conflict(field="extraction_value", extraction_field_id=field_id))
    return conflicts


def find_match(
    citation: models.Citation, pool: list[models.Citation]
) -> models.Citation | None:
    for candidate in pool:
        if is_match(citation, candidate):
            return candidate
    return None


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


def _transfer_reviewer_data(
    db: Session, project: models.ReviewProject, survivor: models.Citation, loser: models.Citation
) -> None:
    """Copies Reviewer-entered data the loser has and the survivor lacks.

    Always a copy onto a new row keyed to the survivor, never a reassignment
    of the loser's own row, so the archived Citation keeps its original data.
    """
    if survivor.screening_decision is None and loser.screening_decision is not None:
        crud.upsert_screening_decision(
            db,
            project,
            survivor.id,
            schemas.ScreeningDecisionCreate(
                decision=loser.screening_decision.decision,
                reason=loser.screening_decision.reason,
            ),
        )
    if survivor.full_text is None and loser.full_text is not None:
        crud.upsert_full_text(
            db,
            survivor.id,
            original_filename=loser.full_text.original_filename,
            file_path=loser.full_text.file_path,
            parsed_text=loser.full_text.parsed_text,
            parse_status=loser.full_text.parse_status,
        )
    if survivor.full_text_decision is None and loser.full_text_decision is not None:
        crud.upsert_full_text_decision(
            db,
            survivor.id,
            schemas.FullTextDecisionCreate(
                decision=loser.full_text_decision.decision,
                reason=loser.full_text_decision.reason,
            ),
        )
    survivor_field_ids = {value.extraction_field_id for value in survivor.extraction_values}
    for value in loser.extraction_values:
        if value.extraction_field_id not in survivor_field_ids:
            crud.upsert_extraction_value(
                db,
                survivor.id,
                value.extraction_field_id,
                schemas.ExtractionValueCreate(value=value.value),
            )


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
    for citation in new_citations:
        held = crud.held_citation_ids(db, project.id)
        pool = [
            c
            for c in crud.list_citations(db, project.id)
            if c.id != citation.id and c.id not in held
        ]
        match = find_match(citation, pool)
        if match is None:
            continue
        conflicts = find_conflicts(match, citation)
        if conflicts:
            crud.create_possible_duplicate(
                db, project.id, survivor_id=match.id, loser_id=citation.id
            )
        else:
            merge_pair(db, project, survivor=match, loser=citation)


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
    if choice.field == "screening_decision":
        crud.upsert_screening_decision(
            db,
            project,
            survivor.id,
            schemas.ScreeningDecisionCreate(
                decision=loser.screening_decision.decision,
                reason=loser.screening_decision.reason,
            ),
        )
    elif choice.field == "full_text_decision":
        crud.upsert_full_text_decision(
            db,
            survivor.id,
            schemas.FullTextDecisionCreate(
                decision=loser.full_text_decision.decision,
                reason=loser.full_text_decision.reason,
            ),
        )
    elif choice.field == "full_text":
        crud.upsert_full_text(
            db,
            survivor.id,
            original_filename=loser.full_text.original_filename,
            file_path=loser.full_text.file_path,
            parsed_text=loser.full_text.parsed_text,
            parse_status=loser.full_text.parse_status,
        )
    elif choice.field == "extraction_value":
        crud.upsert_extraction_value(
            db,
            survivor.id,
            choice.extraction_field_id,
            schemas.ExtractionValueCreate(value=loser.extraction_value_for(choice.extraction_field_id)),
        )


def _validate_choices_match_conflicts(
    conflicts: list[Conflict], choices: list[schemas.ConflictResolutionChoice]
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
    conflict: Conflict, extraction_fields_by_id: dict[uuid.UUID, models.ExtractionField]
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


def to_possible_duplicate_read(
    possible_duplicate: models.PossibleDuplicate,
) -> schemas.PossibleDuplicateRead:
    survivor = possible_duplicate.survivor_citation
    loser = possible_duplicate.loser_citation
    conflicts = find_conflicts(survivor, loser)
    extraction_fields_by_id = {
        field.id: field for field in survivor.review_project.extraction_fields
    }
    return schemas.PossibleDuplicateRead(
        id=possible_duplicate.id,
        survivor=schemas.PossibleDuplicateCitationRead.model_validate(survivor),
        loser=schemas.PossibleDuplicateCitationRead.model_validate(loser),
        conflicting_fields=[_conflict_field_read(c, extraction_fields_by_id) for c in conflicts],
        created_at=possible_duplicate.created_at,
    )


def import_citations(
    db: Session, project: models.ReviewProject, parsed_citations: list[ParsedCitation]
) -> list[models.Citation]:
    """Creates each parsed Citation and runs Duplicate matching against it in turn.

    Rows are created and matched one at a time, not bulk-created up front, so
    that an earlier row in the same batch is always already active by the
    time a later, matching row is checked against it (see process_upload_matches).
    """
    citations = []
    for parsed in parsed_citations:
        [citation] = crud.create_citations(db, project.id, [parsed])
        process_upload_matches(db, project, [citation])
        citations.append(citation)
    return citations
