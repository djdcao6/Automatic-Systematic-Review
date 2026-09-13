from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from asr_backend import crud, models, schemas
from asr_backend.db import get_db
from asr_backend.settings import settings

app = FastAPI(title="Automatic Systematic Review API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/review-projects",
    response_model=schemas.ReviewProjectRead,
    status_code=201,
)
def create_review_project(
    payload: schemas.ReviewProjectCreate, db: Session = Depends(get_db)
) -> models.ReviewProject:
    return crud.create_review_project(db, payload)


@app.get("/review-projects", response_model=list[schemas.ReviewProjectRead])
def list_review_projects(db: Session = Depends(get_db)) -> list[models.ReviewProject]:
    return crud.list_review_projects(db)
