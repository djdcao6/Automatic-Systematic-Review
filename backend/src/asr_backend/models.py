import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
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
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="review_project", cascade="all, delete-orphan"
    )

    @property
    def citations_needing_decision(self) -> int:
        return sum(1 for citation in self.citations if citation.screening_decision is None)


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


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_projects.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    abstract: Mapped[str | None] = mapped_column(String, nullable=True)
    authors: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    review_project: Mapped[ReviewProject] = relationship(back_populates="citations")
    ai_suggestion: Mapped["AISuggestion | None"] = relationship(
        back_populates="citation", uselist=False, cascade="all, delete-orphan"
    )
    screening_decision: Mapped["ScreeningDecision | None"] = relationship(
        back_populates="citation", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def needs_abstract(self) -> bool:
        return self.abstract is None

    @property
    def decision_label(self) -> str:
        return self.screening_decision.decision if self.screening_decision else "unscreened"

    @property
    def screening_reason(self) -> str:
        if self.screening_decision is None:
            return ""
        return self.screening_decision.reason or ""


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citations.id"), unique=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    citation: Mapped[Citation] = relationship(back_populates="ai_suggestion")


class ScreeningDecision(Base):
    __tablename__ = "screening_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citations.id"), unique=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    citation: Mapped[Citation] = relationship(back_populates="screening_decision")
