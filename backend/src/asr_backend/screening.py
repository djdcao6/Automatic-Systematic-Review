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
