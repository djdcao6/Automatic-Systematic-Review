import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from asr_backend.db import Base

_AI_SUGGESTION_UNAVAILABLE = "not_available"


class Reviewer(Base):
    __tablename__ = "reviewers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ReviewProject(Base):
    __tablename__ = "review_projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviewers.id"), nullable=False
    )
    criteria_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merge_mode: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    criteria: Mapped["Criteria | None"] = relationship(
        back_populates="review_project", uselist=False, cascade="all, delete-orphan"
    )
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="review_project", cascade="all, delete-orphan"
    )
    extraction_fields: Mapped[list["ExtractionField"]] = relationship(
        back_populates="review_project",
        cascade="all, delete-orphan",
        order_by="ExtractionField.created_at",
    )
    possible_duplicates: Mapped[list["PossibleDuplicate"]] = relationship(
        back_populates="review_project", cascade="all, delete-orphan"
    )

    @property
    def citations_needing_decision(self) -> int:
        return sum(
            1
            for citation in self.citations
            if not citation.archived and citation.screening_decision is None
        )

    @property
    def active_extraction_fields(self) -> list["ExtractionField"]:
        return [field for field in self.extraction_fields if not field.archived]


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


class ExtractionField(Base):
    __tablename__ = "extraction_fields"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    review_project: Mapped[ReviewProject] = relationship(back_populates="extraction_fields")


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
    source: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    doi: Mapped[str | None] = mapped_column(String, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merged_into_citation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("citations.id"), nullable=True
    )
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
    full_text: Mapped["FullText | None"] = relationship(
        back_populates="citation", uselist=False, cascade="all, delete-orphan"
    )
    full_text_decision: Mapped["FullTextDecision | None"] = relationship(
        back_populates="citation", uselist=False, cascade="all, delete-orphan"
    )
    full_text_suggestion: Mapped["FullTextSuggestion | None"] = relationship(
        back_populates="citation", uselist=False, cascade="all, delete-orphan"
    )
    extraction_values: Mapped[list["ExtractionValue"]] = relationship(
        back_populates="citation",
        cascade="all, delete-orphan",
        order_by="ExtractionValue.created_at",
    )

    @property
    def needs_abstract(self) -> bool:
        return self.abstract is None

    @property
    def screening_resolved(self) -> bool:
        """Whether the title/abstract stage is settled, per ADR 0003.

        A Maybe Screening Decision stands indefinitely unless an Include or
        Exclude Full-Text Decision is later recorded for the Citation, which
        resolves it without altering the original Screening Decision record.
        A Maybe Full-Text Decision carries the same ambiguity forward, so it
        does not resolve anything.
        """
        if self.screening_decision is None:
            return False
        if self.screening_decision.decision != "maybe":
            return True
        return (
            self.full_text_decision is not None
            and self.full_text_decision.decision != "maybe"
        )

    @property
    def decision_label(self) -> str:
        return self.screening_decision.decision if self.screening_decision else "unscreened"

    @property
    def screening_reason(self) -> str:
        if self.screening_decision is None:
            return ""
        return self.screening_decision.reason or ""

    @property
    def ai_suggestion_decision_label(self) -> str:
        return self.ai_suggestion.decision if self.ai_suggestion else _AI_SUGGESTION_UNAVAILABLE

    @property
    def ai_suggestion_reason_label(self) -> str:
        return self.ai_suggestion.reason if self.ai_suggestion else _AI_SUGGESTION_UNAVAILABLE

    @property
    def full_text_decision_label(self) -> str:
        return self.full_text_decision.decision if self.full_text_decision else ""

    @property
    def full_text_reason_label(self) -> str:
        if self.full_text_decision is None:
            return ""
        return self.full_text_decision.reason or ""

    def extraction_value_for(self, extraction_field_id: uuid.UUID) -> str:
        for extraction_value in self.extraction_values:
            if extraction_value.extraction_field_id == extraction_field_id:
                return extraction_value.value
        return ""


class PossibleDuplicate(Base):
    """A Duplicate match held for manual resolution because of a Reviewer-data conflict.

    `survivor_citation` is always the earlier-created side of the pair — the
    same Citation #20's automatic merge would have designated — determined
    once at creation time and never revisited, per ADR 0005.
    """

    __tablename__ = "possible_duplicates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_projects.id"), nullable=False
    )
    survivor_citation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citations.id"), nullable=False
    )
    loser_citation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citations.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    review_project: Mapped[ReviewProject] = relationship(back_populates="possible_duplicates")
    survivor_citation: Mapped[Citation] = relationship(foreign_keys=[survivor_citation_id])
    loser_citation: Mapped[Citation] = relationship(foreign_keys=[loser_citation_id])


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


class FullText(Base):
    __tablename__ = "full_texts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citations.id"), unique=True, nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    parsed_text: Mapped[str | None] = mapped_column(String, nullable=True)
    parse_status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    citation: Mapped[Citation] = relationship(back_populates="full_text")


class FullTextDecision(Base):
    __tablename__ = "full_text_decisions"

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

    citation: Mapped[Citation] = relationship(back_populates="full_text_decision")


class FullTextSuggestion(Base):
    __tablename__ = "full_text_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citations.id"), unique=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    citation: Mapped[Citation] = relationship(back_populates="full_text_suggestion")
    extraction_values: Mapped[list["FullTextSuggestionValue"]] = relationship(
        back_populates="full_text_suggestion",
        cascade="all, delete-orphan",
        order_by="FullTextSuggestionValue.created_at",
    )


class FullTextSuggestionValue(Base):
    __tablename__ = "full_text_suggestion_values"
    __table_args__ = (
        UniqueConstraint("full_text_suggestion_id", "extraction_field_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    full_text_suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("full_text_suggestions.id"), nullable=False
    )
    extraction_field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_fields.id"), nullable=False
    )
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    full_text_suggestion: Mapped[FullTextSuggestion] = relationship(
        back_populates="extraction_values"
    )
    extraction_field: Mapped["ExtractionField"] = relationship()

    @property
    def name(self) -> str:
        return self.extraction_field.name


class ExtractionValue(Base):
    """A Reviewer's recorded value for one Citation x Extraction Field pair.

    Kept separate from FullTextSuggestionValue (the AI-proposed value) so a
    confirmed value is stored distinctly even when it matches the proposal,
    mirroring how AISuggestion and ScreeningDecision stay separate in v1.
    """

    __tablename__ = "extraction_values"
    __table_args__ = (UniqueConstraint("citation_id", "extraction_field_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("citations.id"), nullable=False)
    extraction_field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_fields.id"), nullable=False
    )
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    citation: Mapped[Citation] = relationship(back_populates="extraction_values")
    extraction_field: Mapped["ExtractionField"] = relationship()

    @property
    def name(self) -> str:
        return self.extraction_field.name
