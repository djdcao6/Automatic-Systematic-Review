from sqlalchemy.orm import Session

from asr_backend import crud, models
from asr_backend.ai_suggestion import AISuggester, SuggestionGenerationError

MISSING_ABSTRACT = "missing_abstract"
GENERATION_FAILED = "generation_failed"


async def get_or_generate_suggestion(
    db: Session, citation: models.Citation, suggester: AISuggester
) -> tuple[models.AISuggestion | None, str | None]:
    """Returns the Citation's persisted AI Suggestion, generating one on first access.

    Matches the AI Suggestion domain rule: generated once on demand, then
    persisted and reused on every later view rather than regenerated.
    """
    existing = crud.get_ai_suggestion(db, citation.id)
    if existing is not None:
        return existing, None

    if citation.needs_abstract:
        return None, MISSING_ABSTRACT

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

    suggestion = crud.create_ai_suggestion(db, citation.id, result.decision, result.reason)
    return suggestion, None


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
    is_blind = project.review_mode == "dual" and own_decision is None
    if is_blind or project.review_mode != "dual":
        return own_decision, None, is_blind

    peer_reviewer_id = (
        project.co_reviewer_id
        if reviewer.id == project.owner_reviewer_id
        else project.owner_reviewer_id
    )
    peer_decision = (
        crud.get_screening_decision(db, citation.id, peer_reviewer_id)
        if peer_reviewer_id is not None
        else None
    )
    return own_decision, peer_decision, is_blind
