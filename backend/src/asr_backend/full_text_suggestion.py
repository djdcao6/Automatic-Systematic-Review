from sqlalchemy.orm import Session

from asr_backend import crud, models
from asr_backend.ai_suggestion import AISuggester, ExtractionFieldSpec, SuggestionGenerationError
from asr_backend.full_text import PARSED

NO_FULL_TEXT = "no_full_text"
PARSE_FAILED = "parse_failed"
GENERATION_FAILED = "generation_failed"


async def get_or_generate_full_text_suggestion(
    db: Session,
    citation: models.Citation,
    full_text: models.FullText | None,
    suggester: AISuggester,
) -> tuple[models.FullTextSuggestion | None, str | None]:
    """Returns the Citation's persisted Full-Text Suggestion, generating one on first access.

    Mirrors the AI Suggestion domain rule (asr_backend.screening), but keyed
    to the Full Text: generated once per Full Text version, then persisted
    and reused until the PDF is replaced. Replacing the PDF invalidates the
    prior Suggestion (asr_backend.crud.delete_full_text_suggestion, called
    from the full-text upload route), so the next access here regenerates it.
    """
    existing = crud.get_full_text_suggestion(db, citation.id)
    if existing is not None:
        return existing, None

    if full_text is None:
        return None, NO_FULL_TEXT
    if full_text.parse_status != PARSED:
        return None, PARSE_FAILED

    review_project = citation.review_project
    criteria = review_project.criteria
    active_fields = [field for field in review_project.extraction_fields if not field.archived]

    try:
        result = await suggester.suggest_full_text_decision(
            full_text=full_text.parsed_text or "",
            extraction_fields=[
                ExtractionFieldSpec(
                    id=str(field.id), name=field.name, description=field.description
                )
                for field in active_fields
            ],
            population=criteria.population if criteria else None,
            intervention=criteria.intervention if criteria else None,
            comparison=criteria.comparison if criteria else None,
            outcome=criteria.outcome if criteria else None,
            exclusion_rules=criteria.exclusion_rules if criteria else [],
            notes=criteria.notes if criteria else None,
        )
    except SuggestionGenerationError:
        return None, GENERATION_FAILED

    suggestion = crud.create_full_text_suggestion(
        db,
        citation.id,
        decision=result.decision,
        reason=result.reason,
        extraction_values=result.extraction_values,
        active_fields=active_fields,
    )
    return suggestion, None
