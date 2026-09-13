import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from asr_backend.db import Base


class ReviewProject(Base):
    __tablename__ = "review_projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    criteria_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    criteria: Mapped["Criteria | None"] = relationship(
        back_populates="review_project", uselist=False, cascade="all, delete-orphan"
    )


class Criteria(Base):
    __tablename__ = "criteria"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_projects.id"), unique=True, nullable=False
    )
    population: Mapped[str | None] = mapped_column(String, nullable=True)
    intervention: Mapped[str | None] = mapped_column(String, nullable=True)
    comparison: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    exclusion_rules: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    review_project: Mapped[ReviewProject] = relationship(back_populates="criteria")
