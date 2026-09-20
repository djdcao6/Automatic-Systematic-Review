from sqlalchemy.orm import Session

from asr_backend import crud, models
from asr_backend.ai_suggestion import AISuggester, SuggestionGenerationError
from asr_backend.settings import settings

MISSING_ABSTRACT = "missing_abstract"
GENERATION_FAILED = "generation_failed"


def read_suggestion(
    db: Session, citation: models.Citation
) -> tuple[models.AISuggestion | None, str | None, bool]:
    """Reads a Citation's AI Suggestion state without generating anything.

    Returns (the persisted suggestion, why none can exist, whether one still
    needs generating). Cheap enough for the Citation detail view, which must
    not wait on the model.
    """
    existing = crud.get_ai_suggestion(db, citation.id)
    if existing is not None:
        return existing, None, False
    if citation.needs_abstract:
        return None, MISSING_ABSTRACT, False
    return None, None, True


async def get_or_generate_suggestion(
    db: Session, citation: models.Citation, suggester: AISuggester
) -> tuple[models.AISuggestion | None, str | None]:
    """Returns the Citation's persisted AI Suggestion, generating one on first access.

    Matches the AI Suggestion domain rule: generated once on demand, then
    persisted and reused on every later view rather than regenerated.
    """
    existing, unavailable_reason, needs_generation = read_suggestion(db, citation)
    if not needs_generation:
        return existing, unavailable_reason

    criteria = citation.review_project.criteria
    try:
        result = await suggester.suggest_screening_decision(
            title=citation.title,
            abstract=citation.abstract,
            population=criteria.population if criteria else None,
            intervention=criteria.intervention if criteria else None,
            comparison=criteria.comparison if criteria else None,
            outcome=criteria.outcome if criteria else None,
            exclusion_rules=criteria.exclusion_rules if criteria else [],
            notes=criteria.notes if criteria else None,
        )
    except SuggestionGenerationError:
        return None, GENERATION_FAILED

    suggestion = crud.create_ai_suggestion(
        db, citation.id, result.decision, result.reason, settings.anthropic_model
    )
    return suggestion, None


def is_blind(
    project: models.ReviewProject, own_decision: models.ScreeningDecision | None
) -> bool:
    """Whether a Reviewer must not yet see the peer's decision or the AI Suggestion (ADR 0006).

    True in a Dual project for a Reviewer with no Screening Decision of their own
    on the Citation. Decided per Citation, not per Reviewer: one Reviewer can be
    blind on some Citations and not on others. Every place that shows a Citation's
    peer decision, final decision or AI Suggestion (the detail view, the CSV export,
    the Possible Duplicates list) asks this, so the rule lives in one place.
    """
    return project.review_mode == "dual" and own_decision is None


def resolve_screening_view(
    db: Session,
    project: models.ReviewProject,
    citation: models.Citation,
    reviewer: models.Reviewer,
) -> tuple[models.ScreeningDecision | None, models.ScreeningDecision | None, bool]:
    """Shapes a Citation's Screening Decisions for one viewing Reviewer, per #27/ADR 0006.

    Returns (this Reviewer's own decision, the peer's decision, whether this
    Reviewer is currently blind). In a Dual project, a Reviewer who hasn't
    yet recorded their own decision is blind: the peer's decision is withheld
    regardless of whether it exists yet, and the caller must withhold the AI
    Suggestion too so neither Reviewer's independent judgment is AI-anchored.
    Solo is never blind — its single Reviewer has no peer to withhold.
    """
    own_decision = crud.get_screening_decision(db, citation.id, reviewer.id)
    blind = is_blind(project, own_decision)
    if blind or project.review_mode != "dual":
        return own_decision, None, blind

    peer_reviewer_id = (
        # Falls back to former_co_reviewer_id so a decision already recorded
        # by a since-removed Co-Reviewer (#29) still stays visible to the
        # Owner rather than disappearing once co_reviewer_id is cleared.
        (project.co_reviewer_id or project.former_co_reviewer_id)
        if reviewer.id == project.owner_reviewer_id
        else project.owner_reviewer_id
    )
    peer_decision = (
        crud.get_screening_decision(db, citation.id, peer_reviewer_id)
        if peer_reviewer_id is not None
        else None
    )
    return own_decision, peer_decision, blind
