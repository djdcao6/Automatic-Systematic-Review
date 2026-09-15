import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from asr_backend import models, schemas
from asr_backend.citation_import import ParsedCitation


def get_reviewer(db: Session, reviewer_id: uuid.UUID) -> models.Reviewer | None:
    return db.get(models.Reviewer, reviewer_id)


def get_reviewer_by_email(db: Session, email: str) -> models.Reviewer | None:
    return db.query(models.Reviewer).filter(models.Reviewer.email == email).one_or_none()


def create_reviewer(db: Session, email: str, hashed_password: str) -> models.Reviewer | None:
    stmt = pg_insert(models.Reviewer).values(email=email, hashed_password=hashed_password)
    stmt = stmt.on_conflict_do_nothing(index_elements=[models.Reviewer.email]).returning(
        models.Reviewer.id
    )
    # Atomic INSERT ... ON CONFLICT DO NOTHING, like upsert_criteria, so two
    # concurrent registrations with the same email can't both pass a
    # read-then-write check and one race into an unhandled IntegrityError.
    # RETURNING (rather than rowcount) detects the no-op reliably, since the
    # psycopg driver reports rowcount as -1 for this statement shape.
    inserted_id = db.execute(stmt).scalar_one_or_none()
    if inserted_id is None:
        db.rollback()
        return None
    db.commit()
    return db.get(models.Reviewer, inserted_id)


def get_review_project(db: Session, review_project_id: uuid.UUID) -> models.ReviewProject | None:
    return db.get(models.ReviewProject, review_project_id)


def upsert_criteria(
    db: Session, review_project: models.ReviewProject, payload: schemas.CriteriaUpdate
) -> models.Criteria:
    values = {
        "review_project_id": review_project.id,
        "population": payload.population,
        "intervention": payload.intervention,
        "comparison": payload.comparison,
        "outcome": payload.outcome,
        "exclusion_rules": payload.exclusion_rules,
        "notes": payload.notes,
    }
    stmt = pg_insert(models.Criteria).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.Criteria.review_project_id],
        set_={
            key: stmt.excluded[key] for key in values if key != "review_project_id"
        },
    )
    # A single INSERT ... ON CONFLICT DO UPDATE is atomic at the database level,
    # unlike a read-then-write, which races when two requests both see no
    # existing row for the same review project.
    db.execute(stmt)
    db.commit()
    return (
        db.query(models.Criteria)
        .filter(models.Criteria.review_project_id == review_project.id)
        .one()
    )


def create_review_project(
    db: Session, owner_reviewer_id: uuid.UUID, payload: schemas.ReviewProjectCreate
) -> models.ReviewProject:
    project = models.ReviewProject(
        name=payload.name,
        merge_mode=payload.merge_mode,
        review_mode=payload.review_mode,
        owner_reviewer_id=owner_reviewer_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_review_projects(
    db: Session, owner_reviewer_id: uuid.UUID
) -> list[models.ReviewProject]:
    return list(
        db.query(models.ReviewProject)
        .filter(models.ReviewProject.owner_reviewer_id == owner_reviewer_id)
        .order_by(models.ReviewProject.created_at)
        .all()
    )


def create_extraction_field(
    db: Session, review_project_id: uuid.UUID, payload: schemas.ExtractionFieldCreate
) -> models.ExtractionField:
    field = models.ExtractionField(
        review_project_id=review_project_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


def list_extraction_fields(
    db: Session, review_project_id: uuid.UUID
) -> list[models.ExtractionField]:
    return list(
        db.query(models.ExtractionField)
        .filter(
            models.ExtractionField.review_project_id == review_project_id,
            models.ExtractionField.archived.is_(False),
        )
        .order_by(models.ExtractionField.created_at)
        .all()
    )


def get_extraction_field(
    db: Session, review_project_id: uuid.UUID, extraction_field_id: uuid.UUID
) -> models.ExtractionField | None:
    return (
        db.query(models.ExtractionField)
        .filter(
            models.ExtractionField.id == extraction_field_id,
            models.ExtractionField.review_project_id == review_project_id,
        )
        .one_or_none()
    )


def update_extraction_field(
    db: Session,
    extraction_field: models.ExtractionField,
    payload: schemas.ExtractionFieldUpdate,
) -> models.ExtractionField:
    extraction_field.name = payload.name
    extraction_field.description = payload.description
    db.commit()
    db.refresh(extraction_field)
    return extraction_field


def archive_extraction_field(
    db: Session, extraction_field: models.ExtractionField
) -> models.ExtractionField:
    extraction_field.archived = True
    db.commit()
    db.refresh(extraction_field)
    return extraction_field


def create_citations(
    db: Session, review_project_id: uuid.UUID, parsed_citations: list[ParsedCitation]
) -> list[models.Citation]:
    citations = [
        models.Citation(
            review_project_id=review_project_id,
            title=parsed.title,
            abstract=parsed.abstract,
            authors=parsed.authors,
            year=parsed.year,
            source=parsed.source,
            doi=parsed.doi,
        )
        for parsed in parsed_citations
    ]
    db.add_all(citations)
    db.commit()
    return citations


def list_citations(db: Session, review_project_id: uuid.UUID) -> list[models.Citation]:
    return list(
        db.query(models.Citation)
        .filter(
            models.Citation.review_project_id == review_project_id,
            models.Citation.archived.is_(False),
        )
        .order_by(models.Citation.created_at)
        .all()
    )


def get_citation(
    db: Session, review_project_id: uuid.UUID, citation_id: uuid.UUID
) -> models.Citation | None:
    return (
        db.query(models.Citation)
        .filter(
            models.Citation.id == citation_id,
            models.Citation.review_project_id == review_project_id,
        )
        .one_or_none()
    )


def get_ai_suggestion(db: Session, citation_id: uuid.UUID) -> models.AISuggestion | None:
    return (
        db.query(models.AISuggestion)
        .filter(models.AISuggestion.citation_id == citation_id)
        .one_or_none()
    )


def create_ai_suggestion(
    db: Session, citation_id: uuid.UUID, decision: str, reason: str
) -> models.AISuggestion:
    suggestion = models.AISuggestion(citation_id=citation_id, decision=decision, reason=reason)
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def get_screening_decision(
    db: Session, citation_id: uuid.UUID
) -> models.ScreeningDecision | None:
    return (
        db.query(models.ScreeningDecision)
        .filter(models.ScreeningDecision.citation_id == citation_id)
        .one_or_none()
    )


def upsert_screening_decision(
    db: Session,
    review_project: models.ReviewProject,
    citation_id: uuid.UUID,
    payload: schemas.ScreeningDecisionCreate,
) -> models.ScreeningDecision:
    values = {
        "citation_id": citation_id,
        "decision": payload.decision,
        "reason": payload.reason,
    }
    stmt = pg_insert(models.ScreeningDecision).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.ScreeningDecision.citation_id],
        set_={
            "decision": stmt.excluded.decision,
            "reason": stmt.excluded.reason,
            "updated_at": func.now(),
        },
    )
    # Same atomic INSERT ... ON CONFLICT DO UPDATE pattern as upsert_criteria,
    # since a Screening Decision is editable and this races the same way.
    db.execute(stmt)
    if not review_project.criteria_locked:
        review_project.criteria_locked = True
    db.commit()
    return (
        db.query(models.ScreeningDecision)
        .filter(models.ScreeningDecision.citation_id == citation_id)
        .one()
    )


def get_full_text(db: Session, citation_id: uuid.UUID) -> models.FullText | None:
    return (
        db.query(models.FullText)
        .filter(models.FullText.citation_id == citation_id)
        .one_or_none()
    )


def upsert_full_text(
    db: Session,
    citation_id: uuid.UUID,
    *,
    original_filename: str,
    file_path: str,
    parsed_text: str | None,
    parse_status: str,
) -> models.FullText:
    values = {
        "citation_id": citation_id,
        "original_filename": original_filename,
        "file_path": file_path,
        "parsed_text": parsed_text,
        "parse_status": parse_status,
    }
    stmt = pg_insert(models.FullText).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.FullText.citation_id],
        set_={
            "original_filename": stmt.excluded.original_filename,
            "file_path": stmt.excluded.file_path,
            "parsed_text": stmt.excluded.parsed_text,
            "parse_status": stmt.excluded.parse_status,
            "updated_at": func.now(),
        },
    )
    # Same atomic INSERT ... ON CONFLICT DO UPDATE pattern as upsert_criteria,
    # since replacing a Full Text races the same way as a fresh upload.
    db.execute(stmt)
    db.commit()
    return (
        db.query(models.FullText).filter(models.FullText.citation_id == citation_id).one()
    )


def get_full_text_decision(
    db: Session, citation_id: uuid.UUID
) -> models.FullTextDecision | None:
    return (
        db.query(models.FullTextDecision)
        .filter(models.FullTextDecision.citation_id == citation_id)
        .one_or_none()
    )


def upsert_full_text_decision(
    db: Session,
    citation_id: uuid.UUID,
    payload: schemas.FullTextDecisionCreate,
) -> models.FullTextDecision:
    values = {
        "citation_id": citation_id,
        "decision": payload.decision,
        "reason": payload.reason,
    }
    stmt = pg_insert(models.FullTextDecision).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.FullTextDecision.citation_id],
        set_={
            "decision": stmt.excluded.decision,
            "reason": stmt.excluded.reason,
            "updated_at": func.now(),
        },
    )
    # Same atomic INSERT ... ON CONFLICT DO UPDATE pattern as
    # upsert_screening_decision, since a Full-Text Decision is editable and
    # this races the same way.
    db.execute(stmt)
    db.commit()
    return (
        db.query(models.FullTextDecision)
        .filter(models.FullTextDecision.citation_id == citation_id)
        .one()
    )


def get_full_text_suggestion(
    db: Session, citation_id: uuid.UUID
) -> models.FullTextSuggestion | None:
    return (
        db.query(models.FullTextSuggestion)
        .filter(models.FullTextSuggestion.citation_id == citation_id)
        .one_or_none()
    )


def create_full_text_suggestion(
    db: Session,
    citation_id: uuid.UUID,
    *,
    decision: str,
    reason: str,
    extraction_values: dict[str, str],
    active_fields: list[models.ExtractionField],
) -> models.FullTextSuggestion:
    suggestion = models.FullTextSuggestion(
        citation_id=citation_id, decision=decision, reason=reason
    )
    db.add(suggestion)
    db.flush()

    # Keyed by field id, not name, since Extraction Field names aren't
    # unique — see the matching note in asr_backend.ai_suggestion.
    field_by_id = {str(field.id): field for field in active_fields}
    for field_id, value in extraction_values.items():
        field = field_by_id.get(field_id)
        if field is None:
            continue
        db.add(
            models.FullTextSuggestionValue(
                full_text_suggestion_id=suggestion.id,
                extraction_field_id=field.id,
                value=value,
            )
        )

    db.commit()
    db.refresh(suggestion)
    return suggestion


def delete_full_text_suggestion(db: Session, citation_id: uuid.UUID) -> None:
    """Invalidates a Citation's Full-Text Suggestion, e.g. when its PDF is replaced."""
    suggestion = get_full_text_suggestion(db, citation_id)
    if suggestion is not None:
        db.delete(suggestion)
        db.commit()


def get_extraction_values(db: Session, citation_id: uuid.UUID) -> list[models.ExtractionValue]:
    return list(
        db.query(models.ExtractionValue)
        .filter(models.ExtractionValue.citation_id == citation_id)
        .order_by(models.ExtractionValue.created_at)
        .all()
    )


def upsert_extraction_value(
    db: Session,
    citation_id: uuid.UUID,
    extraction_field_id: uuid.UUID,
    payload: schemas.ExtractionValueCreate,
) -> models.ExtractionValue:
    values = {
        "citation_id": citation_id,
        "extraction_field_id": extraction_field_id,
        "value": payload.value,
    }
    stmt = pg_insert(models.ExtractionValue).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            models.ExtractionValue.citation_id,
            models.ExtractionValue.extraction_field_id,
        ],
        set_={
            "value": stmt.excluded.value,
            "updated_at": func.now(),
        },
    )
    # Same atomic INSERT ... ON CONFLICT DO UPDATE pattern as
    # upsert_screening_decision, since an Extraction Value is editable and
    # this races the same way.
    db.execute(stmt)
    db.commit()
    return (
        db.query(models.ExtractionValue)
        .filter(
            models.ExtractionValue.citation_id == citation_id,
            models.ExtractionValue.extraction_field_id == extraction_field_id,
        )
        .one()
    )


def create_possible_duplicate(
    db: Session, review_project_id: uuid.UUID, survivor_id: uuid.UUID, loser_id: uuid.UUID
) -> models.PossibleDuplicate:
    possible_duplicate = models.PossibleDuplicate(
        review_project_id=review_project_id,
        survivor_citation_id=survivor_id,
        loser_citation_id=loser_id,
    )
    db.add(possible_duplicate)
    db.commit()
    db.refresh(possible_duplicate)
    return possible_duplicate


def list_possible_duplicates(
    db: Session, review_project_id: uuid.UUID, status: str = "pending"
) -> list[models.PossibleDuplicate]:
    return list(
        db.query(models.PossibleDuplicate)
        .filter(
            models.PossibleDuplicate.review_project_id == review_project_id,
            models.PossibleDuplicate.status == status,
        )
        .order_by(models.PossibleDuplicate.created_at)
        .all()
    )


def get_possible_duplicate(
    db: Session, review_project_id: uuid.UUID, possible_duplicate_id: uuid.UUID
) -> models.PossibleDuplicate | None:
    return (
        db.query(models.PossibleDuplicate)
        .filter(
            models.PossibleDuplicate.id == possible_duplicate_id,
            models.PossibleDuplicate.review_project_id == review_project_id,
        )
        .one_or_none()
    )


def set_possible_duplicate_status(
    db: Session, possible_duplicate: models.PossibleDuplicate, status: str
) -> models.PossibleDuplicate:
    possible_duplicate.status = status
    possible_duplicate.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(possible_duplicate)
    return possible_duplicate


def held_citation_ids(db: Session, review_project_id: uuid.UUID) -> set[uuid.UUID]:
    """Citation ids that are one side of an unresolved Possible Duplicate.

    Excluded from matching against new uploads per ticket #21, so a third
    upload can't auto-merge away one side of a pending hold out from under it.
    """
    rows = (
        db.query(
            models.PossibleDuplicate.survivor_citation_id,
            models.PossibleDuplicate.loser_citation_id,
        )
        .filter(
            models.PossibleDuplicate.review_project_id == review_project_id,
            models.PossibleDuplicate.status == "pending",
        )
        .all()
    )
    ids: set[uuid.UUID] = set()
    for survivor_id, loser_id in rows:
        ids.add(survivor_id)
        ids.add(loser_id)
    return ids
