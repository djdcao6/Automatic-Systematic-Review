import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


def _require_non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("name must not be blank")
    return stripped


class ReviewProjectCreate(BaseModel):
    name: str

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


class CitationDetailRead(CitationRead):
    suggestion: SuggestionRead | None = None
    suggestion_unavailable_reason: str | None = None
    screening_decision: ScreeningDecisionRead | None = None
    screening_resolved: bool
    full_text: FullTextRead | None = None
    full_text_decision: FullTextDecisionRead | None = None
    full_text_suggestion: FullTextSuggestionRead | None = None
    full_text_suggestion_unavailable_reason: str | None = None
    extraction_fields: list[ExtractionFieldRead] = []
    extraction_values: list[ExtractionValueRead] = []
