import uuid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from asr_backend import models, schemas
from asr_backend.citation_import import ParsedCitation


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
    db: Session, payload: schemas.ReviewProjectCreate
) -> models.ReviewProject:
    project = models.ReviewProject(name=payload.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_review_projects(db: Session) -> list[models.ReviewProject]:
    return list(db.query(models.ReviewProject).order_by(models.ReviewProject.created_at).all())


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
        )
        for parsed in parsed_citations
    ]
    db.add_all(citations)
    db.commit()
    return citations


def list_citations(db: Session, review_project_id: uuid.UUID) -> list[models.Citation]:
    return list(
        db.query(models.Citation)
        .filter(models.Citation.review_project_id == review_project_id)
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
