from collections import Counter

from asr_backend import models, schemas


def compute_identification_counts(citations: list[models.Citation]) -> dict[str, int]:
    """Per-source, pre-deduplication Identification counts, per #32.

    Every Citation row ever created for the project counts here, including
    one later merged away as a Duplicate — grouped by each row's
    `original_source`, a snapshot of `source` taken at creation and never
    touched afterward. Using the live `source` field instead would double
    count: a Combine-mode merge folds a merged-away loser's databases into
    the surviving Citation's `source`, so the survivor's live value stops
    reflecting only its own original upload.
    """
    counts: Counter[str] = Counter()
    for citation in citations:
        counts.update(citation.original_source)
    return dict(counts)


def compute_duplicates_removed(citations: list[models.Citation]) -> int:
    """Citations actually merged away as a Duplicate, per #32.

    Only a Citation with `merged_into_citation_id` set counts — one still
    sitting in the Possible Duplicate queue, pending or dismissed, hasn't
    been removed.
    """
    return sum(1 for citation in citations if citation.merged_into_citation_id is not None)


def _settled_decision(citation: models.Citation) -> str | None:
    """A Citation's settled title/abstract decision for the funnel, per #32.

    Unlike `Citation.final_screening_decision`, a *pending* Conflict blocks
    this rather than falling back to the Owner's raw decision. That fallback
    is deliberate on `final_screening_decision` itself (existing behavior
    other callers, e.g. Possible Duplicate matching, still rely on), but the
    funnel must reflect the Conflict's resolution once the two Reviewers'
    decisions disagree, not either one's individual call while it's still
    unresolved.

    Nothing is settled until every Reviewer required to screen the Citation has
    decided (#54, ADR 0006). The diagram is one set of numbers for the whole
    project, so if it moved when only one Reviewer had decided, the other, who
    has not decided yet, could read that decision off the counts. Solo has one
    Reviewer, so this changes nothing there.
    """
    if citation.needs_screening_decision:
        return None
    if citation.conflict is not None and citation.conflict.status == "pending":
        return None
    final = citation.final_screening_decision
    return final[0] if final else None


def compute_screening_funnel(citations: list[models.Citation]) -> tuple[int, int, int]:
    """(screened, excluded, pending) over non-archived Citations, per #32.

    `screened` counts every non-archived Citation with a settled decision
    recorded so far (Include, Exclude, or Maybe alike); `excluded` is the
    subset of those decided Exclude; `pending` is every non-archived
    Citation still lacking one, including one blocked on an unresolved
    Conflict.
    """
    screened = 0
    excluded = 0
    pending = 0
    for citation in citations:
        if citation.archived:
            continue
        decision = _settled_decision(citation)
        if decision is None:
            pending += 1
            continue
        screened += 1
        if decision == "exclude":
            excluded += 1
    return screened, excluded, pending


def compute_full_text_funnel(
    citations: list[models.Citation],
) -> tuple[int, dict[str, int], int, int]:
    """(assessed, excluded_by_reason, included, pending) over the full-text funnel, per #33.

    Scoped strictly to non-archived Citations whose settled title/abstract
    decision (`_settled_decision`, same Conflict-aware rule the screening
    funnel uses) is Include or Maybe — this alone is what keeps a Full-Text
    Decision recorded against an Excluded Citation out of every count here,
    without needing a separate check: that Citation is never visited.

    `assessed` counts every in-scope Citation with a Full-Text Decision
    recorded (Include, Exclude, or Maybe alike); `excluded_by_reason` tallies
    the Exclude ones by reason, drawn from the Review Project's locked
    `Criteria.exclusion_rules`; `included` counts only the Include ones;
    `pending` is every in-scope Citation still lacking a Full-Text Decision.
    """
    assessed = 0
    excluded_by_reason: Counter[str] = Counter()
    included = 0
    pending = 0
    for citation in citations:
        if citation.archived:
            continue
        if _settled_decision(citation) not in ("include", "maybe"):
            continue
        full_text_decision = citation.full_text_decision
        if full_text_decision is None:
            pending += 1
            continue
        assessed += 1
        if full_text_decision.decision == "exclude":
            excluded_by_reason[full_text_decision.reason or ""] += 1
        elif full_text_decision.decision == "include":
            included += 1
    return assessed, dict(excluded_by_reason), included, pending


def build_flow_diagram_read(project: models.ReviewProject) -> schemas.FlowDiagramRead:
    citations = project.citations
    screened, excluded, pending = compute_screening_funnel(citations)
    full_text_assessed, full_text_excluded_by_reason, full_text_included, full_text_pending = (
        compute_full_text_funnel(citations)
    )
    return schemas.FlowDiagramRead(
        criteria=(
            schemas.CriteriaRead.model_validate(project.criteria)
            if project.criteria is not None
            else None
        ),
        identification_counts=compute_identification_counts(citations),
        duplicates_removed=compute_duplicates_removed(citations),
        screened=screened,
        excluded=excluded,
        pending=pending,
        full_text_assessed=full_text_assessed,
        full_text_excluded_by_reason=full_text_excluded_by_reason,
        full_text_included=full_text_included,
        full_text_pending=full_text_pending,
    )
