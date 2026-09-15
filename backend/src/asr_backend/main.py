import uuid

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from asr_backend import (
    auth,
    citation_import,
    crud,
    duplicates,
    export,
    full_text,
    full_text_suggestion,
    models,
    schemas,
    screening,
)
from asr_backend.ai_suggestion import AISuggester, get_ai_suggester
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


@app.post("/register", response_model=schemas.ReviewerRead, status_code=201)
def register(payload: schemas.ReviewerCreate, db: Session = Depends(get_db)) -> models.Reviewer:
    hashed_password = auth.hash_password(payload.password)
    reviewer = crud.create_reviewer(db, payload.email, hashed_password)
    if reviewer is None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    return reviewer


@app.post("/login", response_model=schemas.Token)
def login(payload: schemas.ReviewerLogin, db: Session = Depends(get_db)) -> schemas.Token:
    reviewer = crud.get_reviewer_by_email(db, payload.email)
    # Verify against a dummy hash when the email is unknown so an unknown
    # email doesn't return measurably faster than a wrong password would,
    # which would otherwise leak account existence via response timing.
    hashed_password = reviewer.hashed_password if reviewer else auth.DUMMY_PASSWORD_HASH
    password_ok = auth.verify_password(payload.password, hashed_password)
    if reviewer is None or not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token = auth.create_access_token(reviewer.id)
    return schemas.Token(access_token=access_token)


@app.get("/me", response_model=schemas.ReviewerRead)
def get_me(
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
) -> models.Reviewer:
    return reviewer


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
    if project.criteria_locked:
        raise HTTPException(
            status_code=409,
            detail="Criteria are locked after the first Screening Decision",
        )
    return crud.upsert_criteria(db, project, payload)


@app.post(
    "/review-projects/{review_project_id}/extraction-fields",
    response_model=schemas.ExtractionFieldRead,
    status_code=201,
)
def create_extraction_field(
    payload: schemas.ExtractionFieldCreate,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.ExtractionField:
    return crud.create_extraction_field(db, project.id, payload)


@app.get(
    "/review-projects/{review_project_id}/extraction-fields",
    response_model=list[schemas.ExtractionFieldRead],
)
def list_extraction_fields(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> list[models.ExtractionField]:
    return crud.list_extraction_fields(db, project.id)


def get_extraction_field_or_404(
    extraction_field_id: uuid.UUID,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.ExtractionField:
    field = crud.get_extraction_field(db, project.id, extraction_field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="Extraction field not found")
    return field


@app.put(
    "/review-projects/{review_project_id}/extraction-fields/{extraction_field_id}",
    response_model=schemas.ExtractionFieldRead,
)
def update_extraction_field(
    payload: schemas.ExtractionFieldUpdate,
    field: models.ExtractionField = Depends(get_extraction_field_or_404),
    db: Session = Depends(get_db),
) -> models.ExtractionField:
    return crud.update_extraction_field(db, field, payload)


@app.post(
    "/review-projects/{review_project_id}/extraction-fields/{extraction_field_id}/archive",
    response_model=schemas.ExtractionFieldRead,
)
def archive_extraction_field(
    field: models.ExtractionField = Depends(get_extraction_field_or_404),
    db: Session = Depends(get_db),
) -> models.ExtractionField:
    return crud.archive_extraction_field(db, field)


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

    citations = duplicates.import_citations(db, project, parsed.citations)
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


def get_citation_or_404(
    citation_id: uuid.UUID,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.Citation:
    citation = crud.get_citation(db, project.id, citation_id)
    if citation is None:
        raise HTTPException(status_code=404, detail="Citation not found")
    return citation


@app.get(
    "/review-projects/{review_project_id}/citations/{citation_id}",
    response_model=schemas.CitationDetailRead,
)
async def get_citation_detail(
    citation: models.Citation = Depends(get_citation_or_404),
    db: Session = Depends(get_db),
    suggester: AISuggester = Depends(get_ai_suggester),
) -> schemas.CitationDetailRead:
    suggestion, unavailable_reason = await screening.get_or_generate_suggestion(
        db, citation, suggester
    )
    decision = crud.get_screening_decision(db, citation.id)
    existing_full_text = crud.get_full_text(db, citation.id)
    full_text_decision = crud.get_full_text_decision(db, citation.id)
    ft_suggestion, ft_unavailable_reason = await full_text_suggestion.get_or_generate_full_text_suggestion(
        db, citation, existing_full_text, suggester
    )
    extraction_values = crud.get_extraction_values(db, citation.id)
    return schemas.CitationDetailRead(
        id=citation.id,
        title=citation.title,
        abstract=citation.abstract,
        authors=citation.authors,
        year=citation.year,
        source=citation.source,
        needs_abstract=citation.needs_abstract,
        suggestion=suggestion,
        suggestion_unavailable_reason=unavailable_reason,
        screening_decision=decision,
        screening_resolved=citation.screening_resolved,
        full_text=existing_full_text,
        full_text_decision=full_text_decision,
        full_text_suggestion=ft_suggestion,
        full_text_suggestion_unavailable_reason=ft_unavailable_reason,
        extraction_fields=citation.review_project.active_extraction_fields,
        extraction_values=extraction_values,
    )


@app.post(
    "/review-projects/{review_project_id}/citations/{citation_id}/decision",
    response_model=schemas.ScreeningDecisionRead,
)
def record_screening_decision(
    payload: schemas.ScreeningDecisionCreate,
    citation: models.Citation = Depends(get_citation_or_404),
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.ScreeningDecision:
    return crud.upsert_screening_decision(db, project, citation.id, payload)


@app.post(
    "/review-projects/{review_project_id}/citations/{citation_id}/full-text",
    response_model=schemas.FullTextRead,
    status_code=201,
)
async def upload_full_text(
    file: UploadFile,
    citation: models.Citation = Depends(get_citation_or_404),
    db: Session = Depends(get_db),
) -> models.FullText:
    if not full_text.is_pdf_upload(file.filename, file.content_type):
        raise HTTPException(status_code=422, detail="File must be a PDF")

    raw = await file.read()
    parsed_text, parse_status = full_text.extract_text(raw)
    file_path = full_text.save_pdf(citation.id, raw)
    result = crud.upsert_full_text(
        db,
        citation.id,
        original_filename=file.filename or "full-text.pdf",
        file_path=file_path,
        parsed_text=parsed_text,
        parse_status=parse_status,
    )
    # A new PDF is new source content, so any prior Full-Text Suggestion is
    # stale; clearing it here lets the next citation detail view regenerate.
    crud.delete_full_text_suggestion(db, citation.id)
    return result


@app.post(
    "/review-projects/{review_project_id}/citations/{citation_id}/full-text-decision",
    response_model=schemas.FullTextDecisionRead,
)
def record_full_text_decision(
    payload: schemas.FullTextDecisionCreate,
    citation: models.Citation = Depends(get_citation_or_404),
    db: Session = Depends(get_db),
) -> models.FullTextDecision:
    if crud.get_full_text(db, citation.id) is None:
        raise HTTPException(
            status_code=409,
            detail="Citation has no Full Text to record a Full-Text Decision against",
        )
    return crud.upsert_full_text_decision(db, citation.id, payload)


@app.post(
    "/review-projects/{review_project_id}/citations/{citation_id}"
    "/extraction-fields/{extraction_field_id}/value",
    response_model=schemas.ExtractionValueRead,
)
def record_extraction_value(
    payload: schemas.ExtractionValueCreate,
    citation: models.Citation = Depends(get_citation_or_404),
    field: models.ExtractionField = Depends(get_extraction_field_or_404),
    db: Session = Depends(get_db),
) -> models.ExtractionValue:
    if field.archived:
        raise HTTPException(
            status_code=409,
            detail="Cannot record an Extraction Value for an archived Extraction Field",
        )
    return crud.upsert_extraction_value(db, citation.id, field.id, payload)


@app.get("/review-projects/{review_project_id}/citations/{citation_id}/full-text/file")
def download_full_text(
    citation: models.Citation = Depends(get_citation_or_404),
    db: Session = Depends(get_db),
) -> FileResponse:
    record = crud.get_full_text(db, citation.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Full Text not found")
    return FileResponse(
        record.file_path,
        media_type="application/pdf",
        filename=record.original_filename,
        content_disposition_type="inline",
    )


@app.get(
    "/review-projects/{review_project_id}/possible-duplicates",
    response_model=list[schemas.PossibleDuplicateRead],
)
def list_possible_duplicates(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> list[schemas.PossibleDuplicateRead]:
    return [
        duplicates.to_possible_duplicate_read(possible_duplicate)
        for possible_duplicate in crud.list_possible_duplicates(db, project.id)
    ]


def get_possible_duplicate_or_404(
    possible_duplicate_id: uuid.UUID,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.PossibleDuplicate:
    possible_duplicate = crud.get_possible_duplicate(db, project.id, possible_duplicate_id)
    if possible_duplicate is None:
        raise HTTPException(status_code=404, detail="Possible Duplicate not found")
    return possible_duplicate


@app.post(
    "/review-projects/{review_project_id}/possible-duplicates/{possible_duplicate_id}/resolve",
    response_model=schemas.CitationRead,
)
def resolve_possible_duplicate(
    payload: schemas.PossibleDuplicateResolve,
    possible_duplicate: models.PossibleDuplicate = Depends(get_possible_duplicate_or_404),
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.Citation:
    if possible_duplicate.status != "pending":
        raise HTTPException(status_code=409, detail="Possible Duplicate is already settled")
    try:
        return duplicates.resolve_possible_duplicate(
            db, project, possible_duplicate, payload.choices
        )
    except duplicates.ChoicesMismatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/review-projects/{review_project_id}/possible-duplicates/{possible_duplicate_id}/dismiss",
    status_code=204,
)
def dismiss_possible_duplicate(
    possible_duplicate: models.PossibleDuplicate = Depends(get_possible_duplicate_or_404),
    db: Session = Depends(get_db),
) -> None:
    if possible_duplicate.status != "pending":
        raise HTTPException(status_code=409, detail="Possible Duplicate is already settled")
    crud.set_possible_duplicate_status(db, possible_duplicate, "dismissed")


@app.get("/review-projects/{review_project_id}/export")
def export_review_project(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> Response:
    citations = crud.list_citations(db, project.id)
    csv_content = export.build_export_csv(project, citations)
    filename = export.build_export_filename(project)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
