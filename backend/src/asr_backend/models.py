import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from asr_backend.db import Base

_AI_SUGGESTION_UNAVAILABLE = "not_available"
EXTRACTION_FIELD_NAME_INDEX = "uq_extraction_fields_active_name"


class Reviewer(Base):
    __tablename__ = "reviewers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # Set on accounts created through an Invitation (accept-register). Such a
    # Reviewer can join and work in the inviting project but cannot create Review
    # Projects until their email is on the sign-up allowlist (signup.py, #60).
    invited_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # When the Reviewer accepted that abstracts, PDFs and criteria are sent to
    # Anthropic's API (#61). Set at sign-up; null on an account that pre-dates the
    # notice, which is asked once, before its first AI request.
    ai_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Subscription(Base):
    """A Reviewer's Stripe-backed billing relationship, per ADR 0007.

    At most one per Reviewer. `status` mirrors Stripe's subscription status
    verbatim (active, past_due, canceled, ...); Plan is derived from it live
    (billing.derive_plan) rather than stored here, per CONTEXT.md's Plan
    definition. A Reviewer with no row is on the Free Plan.
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviewers.id"), unique=True, nullable=False
    )
    stripe_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    stripe_subscription_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ReviewProject(Base):
    __tablename__ = "review_projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviewers.id"), nullable=False
    )
    co_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviewers.id"), nullable=True
    )
    # Set when the Owner removes a Co-Reviewer (#29), cleared once a
    # replacement joins. Lets a Citation missing that Reviewer's Screening
    # Decision report itself as blocked pending a replacement, distinct from
    # Dual mode before anyone has ever joined (#27), where the same missing
    # decision isn't blocking anything yet.
    former_co_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviewers.id"), nullable=True
    )
    criteria_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merge_mode: Mapped[str] = mapped_column(String, nullable=False)
    review_mode: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    criteria: Mapped["Criteria | None"] = relationship(
        back_populates="review_project", uselist=False, cascade="all, delete-orphan"
    )
    search_terms: Mapped["SearchTerms | None"] = relationship(
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
    invitations: Mapped[list["Invitation"]] = relationship(
        back_populates="review_project", cascade="all, delete-orphan"
    )
    conflicts: Mapped[list["Conflict"]] = relationship(
        back_populates="review_project", cascade="all, delete-orphan"
    )

    @property
    def citations_needing_decision(self) -> int:
        return sum(
            1
            for citation in self.citations
            if not citation.archived and citation.needs_screening_decision
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


class SearchTerms(Base):
    __tablename__ = "search_terms"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_projects.id"), unique=True, nullable=False
    )
    # One list per PICO concept, term lists only (#36) — the combined boolean
    # query is derived on read (search_terms.compute_combined_query), never
    # stored, so editing a term list can't leave a stale combined string behind.
    population_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    intervention_terms: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    comparison_terms: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    outcome_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    review_project: Mapped[ReviewProject] = relationship(back_populates="search_terms")


class ExtractionField(Base):
    __tablename__ = "extraction_fields"
    # At most one active field per name in a Review Project (#67), where names
    # match ignoring case and surrounding whitespace. An archived field keeps its
    # name without blocking a new one, hence the partial index. The migration
    # builds the same index; crud.py turns its refusals into a 409.
    __table_args__ = (
        Index(
            EXTRACTION_FIELD_NAME_INDEX,
            "review_project_id",
            func.lower(func.btrim(text("name"))),
            unique=True,
            postgresql_where=text("NOT archived"),
        ),
    )

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
    # Snapshot of `source` as this row was first created, never touched
    # afterward -- unlike `source` itself, which a Combine-mode Duplicate
    # merge (duplicates.py) extends with a merged-away loser's databases.
    # The PRISMA Flow Diagram's per-source Identification counts (#32) read
    # this instead of `source`, so a survivor's count isn't inflated by
    # databases that arrived via a later merge rather than its own upload.
    original_source: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
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
    screening_decisions: Mapped[list["ScreeningDecision"]] = relationship(
        back_populates="citation", cascade="all, delete-orphan"
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
    conflict: Mapped["Conflict | None"] = relationship(
        back_populates="citation", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def needs_abstract(self) -> bool:
        return self.abstract is None

    def screening_decision_for(self, reviewer_id: uuid.UUID) -> "ScreeningDecision | None":
        for decision in self.screening_decisions:
            if decision.reviewer_id == reviewer_id:
                return decision
        return None

    @property
    def owner_screening_decision(self) -> "ScreeningDecision | None":
        """The Owner's Screening Decision.

        Screening Decisions are now one-per-(Citation, Reviewer) (#27), but
        Possible Duplicate merging and Full-Text resolution still only
        understand a single decision per Citation — they haven't been
        adapted yet for Dual mode's independent per-reviewer decisions. CSV
        export was adapted in #30, reading the Owner's and Co-Reviewer's
        decisions separately via `owner_decision_label`/
        `co_reviewer_decision_label` rather than through this property.
        Until the rest catch up, the Owner's decision stands in as the
        canonical one here, since the Owner always exists (Solo or Dual) and
        has final say resolving a Conflict (#28).
        """
        if not self.screening_decisions:
            return None
        return self.screening_decision_for(self.review_project.owner_reviewer_id)

    @property
    def needs_screening_decision(self) -> bool:
        """Whether any Reviewer required to screen this Citation hasn't yet (#27).

        A removed Co-Reviewer (#29) still counts until a replacement joins —
        their decision is still owed, just currently blocked — so this stays
        true for a blocked Citation rather than reporting it as settled.
        """
        project = self.review_project
        required_reviewer_ids = [project.owner_reviewer_id]
        if project.review_mode == "dual":
            if project.co_reviewer_id is not None:
                required_reviewer_ids.append(project.co_reviewer_id)
            elif project.former_co_reviewer_id is not None:
                required_reviewer_ids.append(project.former_co_reviewer_id)
        return any(
            self.screening_decision_for(reviewer_id) is None
            for reviewer_id in required_reviewer_ids
        )

    @property
    def blocked_pending_co_reviewer(self) -> bool:
        """Whether this Citation awaits a decision from a removed Co-Reviewer (#29).

        True only once a Co-Reviewer has actually been removed and no
        replacement has joined yet, and only for a Citation that removed
        Co-Reviewer never got to decide on. Dual mode before anyone has ever
        joined (#27) is not blocked — there's no removal, just no Co-Reviewer
        yet.
        """
        project = self.review_project
        if project.review_mode != "dual" or project.co_reviewer_id is not None:
            return False
        if project.former_co_reviewer_id is None:
            return False
        return self.screening_decision_for(project.former_co_reviewer_id) is None

    @property
    def final_screening_decision(self) -> tuple[str, str] | None:
        """The Citation's settled (decision, reason), reflecting a resolved Conflict.

        Per #28: once the Owner has resolved a Conflict, that decision — which
        may match neither original — is what counts as final. Otherwise falls
        back to the Owner's own Screening Decision, which is canonical for
        Solo, and for Dual before a Conflict exists or while one is pending.
        """
        if self.conflict is not None and self.conflict.status == "resolved":
            assert self.conflict.resolved_decision is not None
            return self.conflict.resolved_decision, self.conflict.resolved_reason or ""
        decision = self.owner_screening_decision
        if decision is None:
            return None
        return decision.decision, decision.reason or ""

    @property
    def screening_resolved(self) -> bool:
        """Whether the title/abstract stage is settled, per ADR 0003 and #28.

        A pending Conflict leaves this unsettled regardless of either
        Reviewer's own decision, since the two disagree and the Owner hasn't
        yet said which one stands. Otherwise, a Maybe Screening Decision
        stands indefinitely unless an Include or Exclude Full-Text Decision
        is later recorded for the Citation, which resolves it without
        altering the original Screening Decision record. A Maybe Full-Text
        Decision carries the same ambiguity forward, so it does not resolve
        anything.
        """
        if self.conflict is not None and self.conflict.status == "pending":
            return False
        final = self.final_screening_decision
        if final is None:
            return False
        decision, _ = final
        if decision != "maybe":
            return True
        return (
            self.full_text_decision is not None
            and self.full_text_decision.decision != "maybe"
        )

    @property
    def decision_label(self) -> str:
        final = self.final_screening_decision
        return final[0] if final else "unscreened"

    @property
    def screening_reason(self) -> str:
        final = self.final_screening_decision
        return final[1] if final else ""

    @property
    def ai_suggestion_decision_label(self) -> str:
        return self.ai_suggestion.decision if self.ai_suggestion else _AI_SUGGESTION_UNAVAILABLE

    @property
    def ai_suggestion_reason_label(self) -> str:
        return self.ai_suggestion.reason if self.ai_suggestion else _AI_SUGGESTION_UNAVAILABLE

    @property
    def owner_decision_label(self) -> str:
        """The Owner's own Screening Decision, for a Dual export's per-reviewer column (#30).

        Reads the pairing off a resolved/pending Conflict when one exists,
        mirroring `conflicts.to_conflict_read` — robust to a Co-Reviewer
        being removed or replaced after the Conflict formed (#29). Otherwise
        falls back to the Owner id live on the Review Project, since a
        Citation without a Conflict was never re-paired.
        """
        reviewer_id = (
            self.conflict.owner_reviewer_id
            if self.conflict is not None
            else self.review_project.owner_reviewer_id
        )
        decision = self.screening_decision_for(reviewer_id)
        return decision.decision if decision else ""

    @property
    def co_reviewer_decision_label(self) -> str:
        """The Co-Reviewer's own Screening Decision, for a Dual export's per-reviewer column (#30).

        Same Conflict-pairing rationale as `owner_decision_label`. Without a
        Conflict, falls back to the current Co-Reviewer, or the former one
        while a Citation sits blocked pending a replacement (#29).
        """
        if self.conflict is not None:
            reviewer_id = self.conflict.co_reviewer_id
        else:
            project = self.review_project
            reviewer_id = project.co_reviewer_id or project.former_co_reviewer_id
        if reviewer_id is None:
            return ""
        decision = self.screening_decision_for(reviewer_id)
        return decision.decision if decision else ""

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


class Conflict(Base):
    """Held when a Dual Review Project's two Screening Decisions differ, per #28.

    One per Citation — created once the Owner and Co-Reviewer have both
    decided and disagree. `resolved_decision`/`resolved_reason` is the
    Owner's final call, per ADR 0006 not constrained to either original
    value; the two original ScreeningDecision rows are never modified, so
    both stay visible after resolution.

    `owner_reviewer_id`/`co_reviewer_id` snapshot the pairing at creation
    time rather than being read live off the ReviewProject (#29): a
    Co-Reviewer removed (and possibly replaced) after this Conflict formed
    must not change which two ScreeningDecisions it displays.
    """

    __tablename__ = "conflicts"
    __table_args__ = (UniqueConstraint("citation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_projects.id"), nullable=False
    )
    citation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("citations.id"), nullable=False)
    owner_reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviewers.id"), nullable=False
    )
    co_reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviewers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    resolved_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    review_project: Mapped[ReviewProject] = relationship(back_populates="conflicts")
    citation: Mapped[Citation] = relationship(back_populates="conflict")


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


class Invitation(Base):
    """A shareable token an Owner generates to add a Co-Reviewer, per ticket #26.

    Has no automatic expiry — valid until accepted or revoked by the Owner.
    """

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_projects.id"), nullable=False
    )
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    review_project: Mapped[ReviewProject] = relationship(back_populates="invitations")


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citations.id"), unique=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    # The model that wrote it, so suggestions can be compared across models later (#68).
    # "unknown" for rows saved before this was recorded.
    model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    citation: Mapped[Citation] = relationship(back_populates="ai_suggestion")


class ScreeningDecision(Base):
    """A Reviewer's Screening Decision for a Citation.

    One per (Citation, Reviewer) rather than one per Citation, per #27 — in a
    Dual Review Project the Owner and Co-Reviewer each record their own,
    independently of one another.
    """

    __tablename__ = "screening_decisions"
    __table_args__ = (UniqueConstraint("citation_id", "reviewer_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("citations.id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviewers.id"), nullable=False)
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

    citation: Mapped[Citation] = relationship(back_populates="screening_decisions")


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
    # Whether the model was shown only the start of a long PDF (#56). Stored, not
    # derived from the text length, so it stays true to what was sent if the cap changes.
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # The model that wrote it (#68); "unknown" for rows saved before this was recorded.
    model: Mapped[str] = mapped_column(String, nullable=False)
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
