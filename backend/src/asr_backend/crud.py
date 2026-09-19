import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
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


def get_search_terms(
    db: Session, review_project_id: uuid.UUID
) -> models.SearchTerms | None:
    return (
        db.query(models.SearchTerms)
        .filter(models.SearchTerms.review_project_id == review_project_id)
        .one_or_none()
    )


def upsert_search_terms(
    db: Session, review_project: models.ReviewProject, payload: schemas.SearchTermsUpdate
) -> models.SearchTerms:
    values = {
        "review_project_id": review_project.id,
        "population_terms": payload.population_terms,
        "intervention_terms": payload.intervention_terms,
        "comparison_terms": payload.comparison_terms,
        "outcome_terms": payload.outcome_terms,
    }
    stmt = pg_insert(models.SearchTerms).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.SearchTerms.review_project_id],
        set_={
            key: stmt.excluded[key] for key in values if key != "review_project_id"
        },
    )
    # Same atomic INSERT ... ON CONFLICT DO UPDATE pattern as upsert_criteria,
    # so a regenerate racing an edit can't land as a read-then-write.
    db.execute(stmt)
    db.commit()
    return (
        db.query(models.SearchTerms)
        .filter(models.SearchTerms.review_project_id == review_project.id)
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


def count_owned_review_projects(db: Session, reviewer_id: uuid.UUID) -> int:
    """Only Review Projects this Reviewer owns count (#41) — Co-Reviewer
    participation on someone else's project is excluded, per ADR 0007."""
    return (
        db.query(models.ReviewProject)
        .filter(models.ReviewProject.owner_reviewer_id == reviewer_id)
        .count()
    )


def list_review_projects(db: Session, reviewer_id: uuid.UUID) -> list[models.ReviewProject]:
    return list(
        db.query(models.ReviewProject)
        .filter(
            (models.ReviewProject.owner_reviewer_id == reviewer_id)
            | (models.ReviewProject.co_reviewer_id == reviewer_id)
        )
        .order_by(models.ReviewProject.created_at)
        .all()
    )


def remove_co_reviewer(db: Session, project: models.ReviewProject) -> models.ReviewProject:
    """Detaches the current Co-Reviewer, remembered as `former_co_reviewer_id` (#29)."""
    project.former_co_reviewer_id = project.co_reviewer_id
    project.co_reviewer_id = None
    db.commit()
    db.refresh(project)
    return project


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
            original_source=parsed.source,
            doi=parsed.doi,
        )
        for parsed in parsed_citations
    ]
    db.add_all(citations)
    db.commit()
    return citations


# The order Citations appear in, wherever they are listed or stepped through.
# The id breaks ties: a batch upload can stamp several rows with one instant,
# and without it their order, and so every position, would be undefined.
CITATION_ORDER = (models.Citation.created_at, models.Citation.id)


def list_citations(db: Session, review_project_id: uuid.UUID) -> list[models.Citation]:
    return list(
        db.query(models.Citation)
        .filter(
            models.Citation.review_project_id == review_project_id,
            models.Citation.archived.is_(False),
        )
        .order_by(*CITATION_ORDER)
        .all()
    )


@dataclass(frozen=True)
class CitationPlace:
    position: int | None
    total: int
    previous_id: uuid.UUID | None
    next_id: uuid.UUID | None


def get_citation_place(
    db: Session, review_project_id: uuid.UUID, citation: models.Citation
) -> CitationPlace:
    """Where a Citation sits among its Review Project's active Citations.

    One query computes it in the database, so the caller never loads the other
    Citations (abstracts and all) just to count them. An archived Citation is
    not in the list, so it has no position and no neighbours.
    """
    active = (
        models.Citation.review_project_id == review_project_id,
        models.Citation.archived.is_(False),
    )
    ordered = (
        select(
            models.Citation.id.label("id"),
            func.row_number().over(order_by=CITATION_ORDER).label("position"),
            func.count().over().label("total"),
            func.lag(models.Citation.id).over(order_by=CITATION_ORDER).label("previous_id"),
            func.lead(models.Citation.id).over(order_by=CITATION_ORDER).label("next_id"),
        )
        .where(*active)
        .subquery()
    )
    row = db.execute(select(ordered).where(ordered.c.id == citation.id)).one_or_none()
    if row is None:
        total = db.scalar(select(func.count()).select_from(models.Citation).where(*active))
        return CitationPlace(position=None, total=total or 0, previous_id=None, next_id=None)
    return CitationPlace(
        position=row.position, total=row.total, previous_id=row.previous_id, next_id=row.next_id
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
    """Persists a Citation's AI Suggestion, or returns the one a concurrent request saved first.

    Generating takes seconds, so two requests can both find no suggestion and
    both generate. Atomic INSERT ... ON CONFLICT DO NOTHING (as in
    create_reviewer) lets the first save win instead of the second raising an
    IntegrityError, and everyone then sees the same suggestion.
    """
    stmt = (
        pg_insert(models.AISuggestion)
        .values(citation_id=citation_id, decision=decision, reason=reason)
        .on_conflict_do_nothing(index_elements=[models.AISuggestion.citation_id])
        .returning(models.AISuggestion.id)
    )
    inserted_id = db.execute(stmt).scalar_one_or_none()
    if inserted_id is None:
        db.rollback()
        return get_ai_suggestion(db, citation_id)
    db.commit()
    return db.get(models.AISuggestion, inserted_id)


def get_screening_decision(
    db: Session, citation_id: uuid.UUID, reviewer_id: uuid.UUID
) -> models.ScreeningDecision | None:
    return (
        db.query(models.ScreeningDecision)
        .filter(
            models.ScreeningDecision.citation_id == citation_id,
            models.ScreeningDecision.reviewer_id == reviewer_id,
        )
        .one_or_none()
    )


def upsert_screening_decision(
    db: Session,
    review_project: models.ReviewProject,
    citation_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    payload: schemas.ScreeningDecisionCreate,
) -> models.ScreeningDecision:
    values = {
        "citation_id": citation_id,
        "reviewer_id": reviewer_id,
        "decision": payload.decision,
        "reason": payload.reason,
    }
    stmt = pg_insert(models.ScreeningDecision).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            models.ScreeningDecision.citation_id,
            models.ScreeningDecision.reviewer_id,
        ],
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
        .filter(
            models.ScreeningDecision.citation_id == citation_id,
            models.ScreeningDecision.reviewer_id == reviewer_id,
        )
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
    full_text_stamp: datetime,
) -> models.FullTextSuggestion | None:
    """Persists a Citation's Full-Text Suggestion, or returns the one a concurrent request saved first.

    Same race and same answer as create_ai_suggestion: the atomic INSERT ...
    ON CONFLICT DO NOTHING lets the first save win. Only the winner writes the
    Extraction Value rows, so the suggestion and its values always come from
    one generation.

    Generating takes seconds, and the PDF can be replaced meanwhile. The
    suggestion was written from the Full Text as of `full_text_stamp`, so it is
    kept only if that is still the current version, and returns None if not.
    The read takes a FOR SHARE lock held until the commit below, so a
    replacement that starts after the check waits, and the upload route's
    delete_full_text_suggestion then removes what was just saved.
    """
    current_stamp = db.execute(
        select(models.FullText.updated_at)
        .where(models.FullText.citation_id == citation_id)
        .with_for_update(read=True)
    ).scalar_one_or_none()
    if current_stamp != full_text_stamp:
        db.rollback()
        return None

    stmt = (
        pg_insert(models.FullTextSuggestion)
        .values(citation_id=citation_id, decision=decision, reason=reason)
        .on_conflict_do_nothing(index_elements=[models.FullTextSuggestion.citation_id])
        .returning(models.FullTextSuggestion.id)
    )
    inserted_id = db.execute(stmt).scalar_one_or_none()
    if inserted_id is None:
        db.rollback()
        return get_full_text_suggestion(db, citation_id)

    # Keyed by field id, not name, since Extraction Field names aren't
    # unique — see the matching note in asr_backend.ai_suggestion.
    field_by_id = {str(field.id): field for field in active_fields}
    for field_id, value in extraction_values.items():
        field = field_by_id.get(field_id)
        if field is None:
            continue
        db.add(
            models.FullTextSuggestionValue(
                full_text_suggestion_id=inserted_id,
                extraction_field_id=field.id,
                value=value,
            )
        )

    db.commit()
    return db.get(models.FullTextSuggestion, inserted_id)


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


def get_conflict(db: Session, citation_id: uuid.UUID) -> models.Conflict | None:
    return (
        db.query(models.Conflict)
        .filter(models.Conflict.citation_id == citation_id)
        .one_or_none()
    )


def get_conflict_by_id(
    db: Session, review_project_id: uuid.UUID, conflict_id: uuid.UUID
) -> models.Conflict | None:
    return (
        db.query(models.Conflict)
        .filter(
            models.Conflict.id == conflict_id,
            models.Conflict.review_project_id == review_project_id,
        )
        .one_or_none()
    )


def create_conflict(
    db: Session,
    review_project_id: uuid.UUID,
    citation_id: uuid.UUID,
    owner_reviewer_id: uuid.UUID,
    co_reviewer_id: uuid.UUID,
) -> models.Conflict:
    stmt = pg_insert(models.Conflict).values(
        review_project_id=review_project_id,
        citation_id=citation_id,
        owner_reviewer_id=owner_reviewer_id,
        co_reviewer_id=co_reviewer_id,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=[models.Conflict.citation_id]).returning(
        models.Conflict.id
    )
    # Same atomic INSERT ... ON CONFLICT DO NOTHING pattern as create_reviewer,
    # since two decisions racing to complete the pair could both observe that
    # they differ and try to create the Conflict at once.
    inserted_id = db.execute(stmt).scalar_one_or_none()
    if inserted_id is None:
        db.rollback()
        existing = get_conflict(db, citation_id)
        assert existing is not None
        return existing
    db.commit()
    return db.get(models.Conflict, inserted_id)


def list_conflicts(
    db: Session, review_project_id: uuid.UUID, status: str = "pending"
) -> list[models.Conflict]:
    return list(
        db.query(models.Conflict)
        .filter(
            models.Conflict.review_project_id == review_project_id,
            models.Conflict.status == status,
        )
        .order_by(models.Conflict.created_at)
        .all()
    )


def resolve_conflict(
    db: Session, conflict: models.Conflict, decision: str, reason: str | None
) -> models.Conflict:
    conflict.status = "resolved"
    conflict.resolved_decision = decision
    conflict.resolved_reason = reason
    conflict.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(conflict)
    return conflict


def delete_conflict(db: Session, conflict: models.Conflict) -> None:
    db.delete(conflict)
    db.commit()


def create_invitation(db: Session, review_project_id: uuid.UUID) -> models.Invitation:
    invitation = models.Invitation(
        review_project_id=review_project_id, token=secrets.token_urlsafe(32)
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def list_invitations(
    db: Session, review_project_id: uuid.UUID, status: str = "pending"
) -> list[models.Invitation]:
    return list(
        db.query(models.Invitation)
        .filter(
            models.Invitation.review_project_id == review_project_id,
            models.Invitation.status == status,
        )
        .order_by(models.Invitation.created_at)
        .all()
    )


def get_invitation(
    db: Session, review_project_id: uuid.UUID, invitation_id: uuid.UUID
) -> models.Invitation | None:
    return (
        db.query(models.Invitation)
        .filter(
            models.Invitation.id == invitation_id,
            models.Invitation.review_project_id == review_project_id,
        )
        .one_or_none()
    )


def get_invitation_by_token(db: Session, token: str) -> models.Invitation | None:
    return db.query(models.Invitation).filter(models.Invitation.token == token).one_or_none()


def revoke_invitation(db: Session, invitation: models.Invitation) -> models.Invitation:
    invitation.status = "revoked"
    invitation.revoked_at = datetime.now(UTC)
    db.commit()
    db.refresh(invitation)
    return invitation


def get_subscription(db: Session, reviewer_id: uuid.UUID) -> models.Subscription | None:
    return (
        db.query(models.Subscription)
        .filter(models.Subscription.reviewer_id == reviewer_id)
        .one_or_none()
    )


def upsert_subscription(
    db: Session,
    *,
    reviewer_id: uuid.UUID,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    status: str,
    current_period_end: datetime | None,
) -> models.Subscription:
    values = {
        "reviewer_id": reviewer_id,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "status": status,
        "current_period_end": current_period_end,
    }
    stmt = pg_insert(models.Subscription).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.Subscription.reviewer_id],
        set_={
            "stripe_customer_id": stmt.excluded.stripe_customer_id,
            "stripe_subscription_id": stmt.excluded.stripe_subscription_id,
            "status": stmt.excluded.status,
            "current_period_end": stmt.excluded.current_period_end,
            "updated_at": func.now(),
        },
    )
    # Same atomic INSERT ... ON CONFLICT DO UPDATE pattern as upsert_full_text,
    # since a webhook retried or delivered out of order races a concurrent
    # delivery of the same or a later event for the same Reviewer.
    db.execute(stmt)
    db.commit()
    return db.query(models.Subscription).filter(
        models.Subscription.reviewer_id == reviewer_id
    ).one()
