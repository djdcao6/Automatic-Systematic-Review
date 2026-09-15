import re

from sqlalchemy.orm import Session

from asr_backend import crud, models, schemas
from asr_backend.citation_import import ParsedCitation

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


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


def has_conflict(a: models.Citation, b: models.Citation) -> bool:
    """Whether a matched pair already carries conflicting Reviewer-entered data.

    Checked field-by-field (Screening Decision, Full-Text Decision, each
    Extraction Field, Full Text) rather than citation-wide, though a single
    conflicting field holds the entire pair from merging.
    """
    if (
        a.screening_decision is not None
        and b.screening_decision is not None
        and a.screening_decision.decision != b.screening_decision.decision
    ):
        return True
    if (
        a.full_text_decision is not None
        and b.full_text_decision is not None
        and a.full_text_decision.decision != b.full_text_decision.decision
    ):
        return True
    if a.full_text is not None and b.full_text is not None:
        return True
    a_values = {value.extraction_field_id: value.value for value in a.extraction_values}
    b_values = {value.extraction_field_id: value.value for value in b.extraction_values}
    for field_id, value in a_values.items():
        if field_id in b_values and b_values[field_id] != value:
            return True
    return False


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
    """Runs Duplicate matching for already-persisted Citations, merging non-conflicting matches.

    Each given Citation is checked against the Review Project's other
    currently-active Citations. The earlier-created side of any match always
    survives — which holds true here only because the caller guarantees each
    given Citation was already active in the database before any Citation
    created after it was. Bulk-persisting a whole batch and then calling this
    once over all of it would violate that guarantee, since two same-batch
    rows would each see the other as already active; import_citations avoids
    that by creating and matching one row at a time.
    """
    for citation in new_citations:
        pool = [c for c in crud.list_citations(db, project.id) if c.id != citation.id]
        match = find_match(citation, pool)
        if match is not None and not has_conflict(match, citation):
            merge_pair(db, project, survivor=match, loser=citation)


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
