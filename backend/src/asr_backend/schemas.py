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


class ReviewProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    criteria_locked: bool
    created_at: datetime
