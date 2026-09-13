import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ReviewProjectCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


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
