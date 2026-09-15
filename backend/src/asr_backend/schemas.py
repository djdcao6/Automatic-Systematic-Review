import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _require_non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("name must not be blank")
    return stripped


def _normalize_email(value: EmailStr) -> str:
    return value.strip().lower()


class ReviewerCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return _normalize_email(value)


class ReviewerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime


class ReviewerLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return _normalize_email(value)


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class ReviewProjectCreate(BaseModel):
    name: str
    merge_mode: Literal["combine", "keep_first"]
    review_mode: Literal["solo", "dual"]

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return _require_non_blank(value)


class CriteriaUpdate(BaseModel):
    population: str | None = None
    intervention: str | None = None
    comparison: str | None = None
    outcome: str | None = None
    exclusion_rules: list[str] = []
    notes: str | None = None


class CriteriaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    population: str | None
    intervention: str | None
    comparison: str | None
    outcome: str | None
    exclusion_rules: list[str]
    notes: str | None


class ReviewProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    criteria_locked: bool
    merge_mode: Literal["combine", "keep_first"]
    review_mode: Literal["solo", "dual"]
    owner_reviewer_id: uuid.UUID
    co_reviewer_id: uuid.UUID | None
    created_at: datetime


class ReviewProjectDetailRead(ReviewProjectRead):
    criteria: CriteriaRead | None = None
    citations_needing_decision: int


class ExtractionFieldCreate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return _require_non_blank(value)


class ExtractionFieldUpdate(ExtractionFieldCreate):
    pass


class ExtractionFieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    abstract: str | None
    authors: list[str]
    year: int | None
    source: list[str]
    needs_abstract: bool


class CitationUploadSkipped(BaseModel):
    row: int
    reason: str


class CitationUploadResult(BaseModel):
    created: int
    skipped: list[CitationUploadSkipped]


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: Literal["include", "exclude", "maybe"]
    reason: str


class ScreeningDecisionCreate(BaseModel):
    decision: Literal["include", "exclude", "maybe"]
    reason: str | None = None


class ScreeningDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: Literal["include", "exclude", "maybe"]
    reason: str | None
    created_at: datetime
    updated_at: datetime


class FullTextRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    original_filename: str
    parse_status: Literal["parsed", "parse_failed"]
    created_at: datetime
    updated_at: datetime


class FullTextDecisionCreate(BaseModel):
    decision: Literal["include", "exclude", "maybe"]
    reason: str | None = None


class FullTextDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: Literal["include", "exclude", "maybe"]
    reason: str | None
    created_at: datetime
    updated_at: datetime


class ExtractionValueSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    extraction_field_id: uuid.UUID
    name: str
    value: str


class FullTextSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: Literal["include", "exclude", "maybe"]
    reason: str
    extraction_values: list[ExtractionValueSuggestionRead]


class ExtractionValueCreate(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        return _require_non_blank(value)


class ExtractionValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    extraction_field_id: uuid.UUID
    name: str
    value: str
    created_at: datetime
    updated_at: datetime


ConflictFieldName = Literal["screening_decision", "full_text_decision", "full_text", "extraction_value"]


class ConflictFieldRead(BaseModel):
    field: ConflictFieldName
    extraction_field_id: uuid.UUID | None = None
    extraction_field_name: str | None = None


class PossibleDuplicateCitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    abstract: str | None
    authors: list[str]
    year: int | None
    source: list[str]
    doi: str | None
    # Reads Citation.owner_screening_decision — Possible Duplicate merging
    # hasn't been adapted for Dual mode's per-reviewer decisions yet (#28/#30).
    screening_decision: ScreeningDecisionRead | None = Field(
        default=None, validation_alias="owner_screening_decision"
    )
    full_text_decision: FullTextDecisionRead | None = None
    full_text: FullTextRead | None = None
    extraction_values: list[ExtractionValueRead] = []


class ConflictCitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str


class ConflictRead(BaseModel):
    id: uuid.UUID
    citation: ConflictCitationRead
    owner_decision: ScreeningDecisionRead
    co_reviewer_decision: ScreeningDecisionRead
    created_at: datetime


class ConflictResolve(BaseModel):
    decision: Literal["include", "exclude", "maybe"]
    reason: str | None = None


class ConflictResolvedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["resolved"]
    resolved_decision: Literal["include", "exclude", "maybe"]
    resolved_reason: str | None
    resolved_at: datetime


class PossibleDuplicateRead(BaseModel):
    id: uuid.UUID
    survivor: PossibleDuplicateCitationRead
    loser: PossibleDuplicateCitationRead
    conflicting_fields: list[ConflictFieldRead]
    created_at: datetime


class ConflictResolutionChoice(BaseModel):
    field: ConflictFieldName
    extraction_field_id: uuid.UUID | None = None
    winner: Literal["survivor", "loser"]


class PossibleDuplicateResolve(BaseModel):
    choices: list[ConflictResolutionChoice]


InvitationStatus = Literal["pending", "accepted", "revoked"]


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    token: str
    status: InvitationStatus
    created_at: datetime


class InvitationPublicRead(BaseModel):
    review_project_name: str
    status: InvitationStatus


class InvitationAcceptRead(Token):
    review_project_id: uuid.UUID


class CitationDetailRead(CitationRead):
    suggestion: SuggestionRead | None = None
    suggestion_unavailable_reason: str | None = None
    screening_decision: ScreeningDecisionRead | None = None
    peer_screening_decision: ScreeningDecisionRead | None = None
    screening_blind: bool = False
    screening_resolved: bool
    full_text: FullTextRead | None = None
    full_text_decision: FullTextDecisionRead | None = None
    full_text_suggestion: FullTextSuggestionRead | None = None
    full_text_suggestion_unavailable_reason: str | None = None
    extraction_fields: list[ExtractionFieldRead] = []
    extraction_values: list[ExtractionValueRead] = []
