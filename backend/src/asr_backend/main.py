import uuid

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from asr_backend import citation_import, crud, models, schemas
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


def get_review_project_or_404(
    review_project_id: uuid.UUID, db: Session = Depends(get_db)
) -> models.ReviewProject:
    project = crud.get_review_project(db, review_project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Review project not found")
    return project


@app.get("/review-projects/{review_project_id}", response_model=schemas.ReviewProjectDetailRead)
def get_review_project(
    project: models.ReviewProject = Depends(get_review_project_or_404),
) -> models.ReviewProject:
    return project


@app.put(
    "/review-projects/{review_project_id}/criteria",
    response_model=schemas.CriteriaRead,
)
def save_criteria(
    payload: schemas.CriteriaUpdate,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.Criteria:
    return crud.upsert_criteria(db, project, payload)


@app.post(
    "/review-projects/{review_project_id}/citations",
    response_model=schemas.CitationUploadResult,
    status_code=201,
)
async def upload_citations(
    file: UploadFile,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> schemas.CitationUploadResult:
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded") from exc

    try:
        parsed = citation_import.parse_upload(file.filename or "", content)
    except citation_import.UnsupportedFileType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    citations = crud.create_citations(db, project.id, parsed.citations)
    return schemas.CitationUploadResult(
        created=len(citations),
        skipped=[
            schemas.CitationUploadSkipped(row=row, reason=reason)
            for row, reason in parsed.skipped
        ],
    )


@app.get(
    "/review-projects/{review_project_id}/citations",
    response_model=list[schemas.CitationRead],
)
def list_citations(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> list[models.Citation]:
    return crud.list_citations(db, project.id)
