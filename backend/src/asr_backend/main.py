import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from asr_backend import (
    auth,
    billing,
    citation_import,
    conflicts,
    crud,
    duplicates,
    export,
    flow_diagram,
    full_text,
    full_text_suggestion,
    invitations,
    models,
    schemas,
    screening,
    search_terms,
)
from asr_backend.ai_suggestion import AISuggester, get_ai_suggester
from asr_backend.db import get_db
from asr_backend.search_terms import (
    NoPicoFieldPopulatedError,
    SearchTermsGenerationError,
    SearchTermsGenerator,
    get_search_terms_generator,
)
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


def require_billing_enabled() -> None:
    """Gates every Reviewer-facing billing endpoint per #39's dark launch.

    While `billing_enabled` is False, these 404 exactly like a route that
    doesn't exist, rather than exposing Plan/Subscription state, so the
    Account/Billing page has nothing to show. The webhook endpoint is
    intentionally not gated by this — it's server-to-server, verified by
    Stripe's signature rather than a Reviewer session.
    """
    if not settings.billing_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


@app.get(
    "/me/subscription",
    response_model=schemas.SubscriptionRead,
    dependencies=[Depends(require_billing_enabled)],
)
def get_my_subscription(
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
) -> schemas.SubscriptionRead:
    subscription = crud.get_subscription(db, reviewer.id)
    return schemas.SubscriptionRead(
        plan=billing.derive_plan(subscription),
        status=subscription.status if subscription else None,
    )


@app.post(
    "/billing/checkout-session",
    response_model=schemas.CheckoutSessionRead,
    dependencies=[Depends(require_billing_enabled)],
)
def create_checkout_session(
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
    gateway: billing.StripeGateway = Depends(billing.get_stripe_gateway),
) -> schemas.CheckoutSessionRead:
    existing = crud.get_subscription(db, reviewer.id)
    session = gateway.create_checkout_session(
        reviewer_id=reviewer.id,
        reviewer_email=reviewer.email,
        customer_id=existing.stripe_customer_id if existing else None,
        success_url=f"{settings.frontend_origin}/account?checkout=success",
        cancel_url=f"{settings.frontend_origin}/account?checkout=cancel",
    )
    return schemas.CheckoutSessionRead(url=session.url)


@app.post(
    "/billing/portal-session",
    response_model=schemas.PortalSessionRead,
    dependencies=[Depends(require_billing_enabled)],
)
def create_portal_session(
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
    gateway: billing.StripeGateway = Depends(billing.get_stripe_gateway),
) -> schemas.PortalSessionRead:
    subscription = crud.get_subscription(db, reviewer.id)
    try:
        billing.require_paid_plan(subscription)
    except billing.PlanNotPaidError as exc:
        raise HTTPException(
            status_code=403, detail="Only a Paid Reviewer can manage their subscription"
        ) from exc
    session = gateway.create_portal_session(
        customer_id=subscription.stripe_customer_id,
        return_url=f"{settings.frontend_origin}/account",
    )
    return schemas.PortalSessionRead(url=session.url)


@app.post("/billing/webhook", status_code=204)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    gateway: billing.StripeGateway = Depends(billing.get_stripe_gateway),
) -> None:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        billing.handle_webhook_event(db, gateway, payload, sig_header)
    except billing.WebhookSignatureError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc


def get_invitation_by_token_or_404(
    token: str, db: Session = Depends(get_db)
) -> models.Invitation:
    invitation = crud.get_invitation_by_token(db, token)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return invitation


@app.get("/invitations/{token}", response_model=schemas.InvitationPublicRead)
def get_invitation_public(
    invitation: models.Invitation = Depends(get_invitation_by_token_or_404),
) -> schemas.InvitationPublicRead:
    return schemas.InvitationPublicRead(
        review_project_name=invitation.review_project.name,
        status=invitation.status,
    )


@app.post(
    "/invitations/{token}/accept-register",
    response_model=schemas.InvitationAcceptRead,
)
def accept_invitation_by_registering(
    payload: schemas.ReviewerCreate,
    invitation: models.Invitation = Depends(get_invitation_by_token_or_404),
    db: Session = Depends(get_db),
) -> schemas.InvitationAcceptRead:
    # Both checked before creating an account, so a revoked/already-accepted
    # link, or one for a project that already has a Co-Reviewer, can't leave
    # behind a Reviewer account no Invitation actually admits. accept_invitation
    # still re-checks both atomically below, since a concurrent accept can slip
    # in between this check and that one.
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation is no longer valid")
    if invitation.review_project.co_reviewer_id is not None:
        raise HTTPException(status_code=409, detail="Review Project already has a Co-Reviewer")
    hashed_password = auth.hash_password(payload.password)
    reviewer = crud.create_reviewer(db, payload.email, hashed_password)
    if reviewer is None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    try:
        project = invitations.accept_invitation(db, invitation, reviewer.id)
    except invitations.InvitationNotAcceptable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    access_token = auth.create_access_token(reviewer.id)
    return schemas.InvitationAcceptRead(access_token=access_token, review_project_id=project.id)


@app.post(
    "/invitations/{token}/accept-login",
    response_model=schemas.InvitationAcceptRead,
)
def accept_invitation_by_logging_in(
    payload: schemas.ReviewerLogin,
    invitation: models.Invitation = Depends(get_invitation_by_token_or_404),
    db: Session = Depends(get_db),
) -> schemas.InvitationAcceptRead:
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation is no longer valid")
    reviewer = crud.get_reviewer_by_email(db, payload.email)
    # Same dummy-hash timing guard as /login.
    hashed_password = reviewer.hashed_password if reviewer else auth.DUMMY_PASSWORD_HASH
    password_ok = auth.verify_password(payload.password, hashed_password)
    if reviewer is None or not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    try:
        project = invitations.accept_invitation(db, invitation, reviewer.id)
    except invitations.InvitationNotAcceptable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    access_token = auth.create_access_token(reviewer.id)
    return schemas.InvitationAcceptRead(access_token=access_token, review_project_id=project.id)


@app.post(
    "/review-projects",
    response_model=schemas.ReviewProjectRead,
    status_code=201,
)
def create_review_project(
    payload: schemas.ReviewProjectCreate,
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
) -> models.ReviewProject:
    try:
        billing.check_review_project_cap(db, reviewer.id)
    except billing.ReviewProjectCapError as exc:
        raise HTTPException(
            status_code=403,
            detail=(
                "Free Plan is limited to 1 Review Project. "
                "Upgrade on the Account/Billing page to create more."
            ),
        ) from exc
    return crud.create_review_project(db, reviewer.id, payload)


@app.get("/review-projects", response_model=list[schemas.ReviewProjectRead])
def list_review_projects(
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
) -> list[models.ReviewProject]:
    return crud.list_review_projects(db, reviewer.id)


def get_review_project_or_404(
    review_project_id: uuid.UUID,
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
) -> models.ReviewProject:
    project = crud.get_review_project(db, review_project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Review project not found")
    if reviewer.id not in (project.owner_reviewer_id, project.co_reviewer_id):
        raise HTTPException(status_code=403, detail="Not authorized for this review project")
    return project


def require_owner(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
) -> models.ReviewProject:
    """Narrows access to the Owner alone, e.g. for managing Invitations (#26)."""
    if reviewer.id != project.owner_reviewer_id:
        raise HTTPException(status_code=403, detail="Only the Owner can perform this action")
    return project


@app.get("/review-projects/{review_project_id}", response_model=schemas.ReviewProjectDetailRead)
def get_review_project(
    project: models.ReviewProject = Depends(get_review_project_or_404),
) -> models.ReviewProject:
    return project


@app.post(
    "/review-projects/{review_project_id}/invitations",
    response_model=schemas.InvitationRead,
    status_code=201,
)
def create_invitation(
    project: models.ReviewProject = Depends(require_owner),
    db: Session = Depends(get_db),
) -> models.Invitation:
    if project.review_mode != "dual":
        raise HTTPException(
            status_code=409, detail="A Solo Review Project has no Invitation capability"
        )
    if project.co_reviewer_id is not None:
        raise HTTPException(
            status_code=409, detail="Review Project already has a Co-Reviewer"
        )
    return crud.create_invitation(db, project.id)


@app.get(
    "/review-projects/{review_project_id}/invitations",
    response_model=list[schemas.InvitationRead],
)
def list_invitations(
    project: models.ReviewProject = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[models.Invitation]:
    return crud.list_invitations(db, project.id)


@app.post(
    "/review-projects/{review_project_id}/invitations/{invitation_id}/revoke",
    response_model=schemas.InvitationRead,
)
def revoke_invitation(
    invitation_id: uuid.UUID,
    project: models.ReviewProject = Depends(require_owner),
    db: Session = Depends(get_db),
) -> models.Invitation:
    invitation = crud.get_invitation(db, project.id, invitation_id)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation is already settled")
    return crud.revoke_invitation(db, invitation)


@app.post(
    "/review-projects/{review_project_id}/co-reviewer/remove",
    response_model=schemas.ReviewProjectRead,
)
def remove_co_reviewer(
    project: models.ReviewProject = Depends(require_owner),
    db: Session = Depends(get_db),
) -> models.ReviewProject:
    if project.co_reviewer_id is None:
        raise HTTPException(
            status_code=409, detail="Review Project has no Co-Reviewer to remove"
        )
    return crud.remove_co_reviewer(db, project)


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
    "/review-projects/{review_project_id}/search-terms",
    response_model=schemas.SearchTermsRead,
    status_code=201,
)
async def generate_search_terms(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    generator: SearchTermsGenerator = Depends(get_search_terms_generator),
    db: Session = Depends(get_db),
) -> schemas.SearchTermsRead:
    # Available regardless of criteria_locked (#36) — unlike Criteria itself,
    # Search Terms have no lock of their own to check.
    try:
        record = await search_terms.generate_and_persist(db, project, generator)
    except NoPicoFieldPopulatedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SearchTermsGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return search_terms.to_read_schema(record)


@app.get(
    "/review-projects/{review_project_id}/search-terms",
    response_model=schemas.SearchTermsRead,
)
def get_search_terms(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> schemas.SearchTermsRead:
    record = crud.get_search_terms(db, project.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Search terms not found")
    return search_terms.to_read_schema(record)


@app.put(
    "/review-projects/{review_project_id}/search-terms",
    response_model=schemas.SearchTermsRead,
)
def update_search_terms(
    payload: schemas.SearchTermsUpdate,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> schemas.SearchTermsRead:
    record = crud.upsert_search_terms(db, project, payload)
    return search_terms.to_read_schema(record)


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

    created_ids = duplicates.import_citations(db, project, parsed.citations)
    return schemas.CitationUploadResult(
        created=len(created_ids),
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
    project: models.ReviewProject = Depends(get_review_project_or_404),
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
    suggester: AISuggester = Depends(get_ai_suggester),
) -> schemas.CitationDetailRead:
    suggestion, unavailable_reason, needs_generation = screening.read_suggestion(db, citation)
    own_decision, peer_decision, is_blind = screening.resolve_screening_view(
        db, project, citation, reviewer
    )
    existing_full_text = crud.get_full_text(db, citation.id)
    full_text_decision = crud.get_full_text_decision(db, citation.id)
    ft_suggestion, ft_unavailable_reason = await full_text_suggestion.get_or_generate_full_text_suggestion(
        db, citation, existing_full_text, suggester
    )
    extraction_values = crud.get_extraction_values(db, citation.id)
    place = crud.get_citation_place(db, project.id, citation)
    return schemas.CitationDetailRead(
        id=citation.id,
        title=citation.title,
        abstract=citation.abstract,
        authors=citation.authors,
        year=citation.year,
        source=citation.source,
        needs_abstract=citation.needs_abstract,
        blocked_pending_co_reviewer=citation.blocked_pending_co_reviewer,
        position=place.position,
        total=place.total,
        previous_citation_id=place.previous_id,
        next_citation_id=place.next_id,
        suggestion=suggestion if not is_blind else None,
        suggestion_unavailable_reason=unavailable_reason if not is_blind else None,
        suggestion_needs_generation=needs_generation,
        screening_decision=own_decision,
        peer_screening_decision=peer_decision,
        screening_blind=is_blind,
        screening_resolved=citation.screening_resolved,
        full_text=existing_full_text,
        full_text_decision=full_text_decision,
        full_text_suggestion=ft_suggestion,
        full_text_suggestion_unavailable_reason=ft_unavailable_reason,
        extraction_fields=citation.review_project.active_extraction_fields,
        extraction_values=extraction_values,
    )


@app.post(
    "/review-projects/{review_project_id}/citations/{citation_id}/suggestion",
    response_model=schemas.SuggestionOutcomeRead,
)
async def generate_citation_suggestion(
    citation: models.Citation = Depends(get_citation_or_404),
    project: models.ReviewProject = Depends(get_review_project_or_404),
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
    suggester: AISuggester = Depends(get_ai_suggester),
) -> schemas.SuggestionOutcomeRead:
    suggestion, unavailable_reason = await screening.get_or_generate_suggestion(
        db, citation, suggester
    )
    # A blind Reviewer's request still generates and keeps the suggestion, so it
    # is ready when they reveal, but nothing about it is sent back (#27, ADR 0006).
    _, _, is_blind = screening.resolve_screening_view(db, project, citation, reviewer)
    if is_blind:
        return schemas.SuggestionOutcomeRead()
    return schemas.SuggestionOutcomeRead(
        suggestion=suggestion, suggestion_unavailable_reason=unavailable_reason
    )


@app.post(
    "/review-projects/{review_project_id}/citations/{citation_id}/decision",
    response_model=schemas.ScreeningDecisionRead,
)
def record_screening_decision(
    payload: schemas.ScreeningDecisionCreate,
    citation: models.Citation = Depends(get_citation_or_404),
    project: models.ReviewProject = Depends(get_review_project_or_404),
    reviewer: models.Reviewer = Depends(auth.get_current_reviewer),
    db: Session = Depends(get_db),
) -> models.ScreeningDecision:
    result = crud.upsert_screening_decision(db, project, citation.id, reviewer.id, payload)
    conflicts.sync_conflict(db, project, citation)
    return result


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


@app.get(
    "/review-projects/{review_project_id}/conflicts",
    response_model=list[schemas.ConflictRead],
)
def list_conflicts(
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> list[schemas.ConflictRead]:
    return [conflicts.to_conflict_read(c) for c in crud.list_conflicts(db, project.id)]


def get_conflict_or_404(
    conflict_id: uuid.UUID,
    project: models.ReviewProject = Depends(get_review_project_or_404),
    db: Session = Depends(get_db),
) -> models.Conflict:
    conflict = crud.get_conflict_by_id(db, project.id, conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return conflict


@app.post(
    "/review-projects/{review_project_id}/conflicts/{conflict_id}/resolve",
    response_model=schemas.ConflictResolvedRead,
)
def resolve_conflict(
    payload: schemas.ConflictResolve,
    conflict: models.Conflict = Depends(get_conflict_or_404),
    project: models.ReviewProject = Depends(require_owner),
    db: Session = Depends(get_db),
) -> models.Conflict:
    if conflict.status != "pending":
        raise HTTPException(status_code=409, detail="Conflict is already resolved")
    return crud.resolve_conflict(db, conflict, payload.decision, payload.reason)


@app.get(
    "/review-projects/{review_project_id}/flow-diagram",
    response_model=schemas.FlowDiagramRead,
)
def get_flow_diagram(
    project: models.ReviewProject = Depends(get_review_project_or_404),
) -> schemas.FlowDiagramRead:
    return flow_diagram.build_flow_diagram_read(project)


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
