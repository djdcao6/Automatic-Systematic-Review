from sqlalchemy.orm import Session

from asr_backend import models, schemas


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
