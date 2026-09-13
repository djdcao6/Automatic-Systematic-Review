import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from asr_backend import models, schemas


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
