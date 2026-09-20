import asyncio
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from asr_backend import crud, models
from asr_backend.ai_suggestion import AISuggester, ExtractionFieldSpec, SuggestionGenerationError
from asr_backend.full_text import PARSED
from asr_backend.settings import settings

NO_FULL_TEXT = "no_full_text"
PARSE_FAILED = "parse_failed"
GENERATION_FAILED = "generation_failed"
GENERATION_WAIT_SECONDS = 0.1
# A model call that hangs must not hold the generation lock, or keep every other
# request for the Citation polling, for the SDK's default of ten minutes and
# retries. The wait limit is longer than one call so a follower can outlast a
# leader that is merely slow, but not one that is stuck.
GENERATION_TIMEOUT_SECONDS = 90
GENERATION_WAIT_LIMIT_SECONDS = 120


def read_full_text_suggestion(
    db: Session, citation: models.Citation, full_text: models.FullText | None
) -> tuple[models.FullTextSuggestion | None, str | None, bool]:
    """Reads a Citation's Full-Text Suggestion state without generating anything.

    Returns (the persisted suggestion, why none can exist, whether one still
    needs generating). Cheap enough for the Citation detail view, which must
    not wait on the model.
    """
    existing = crud.get_full_text_suggestion(db, citation.id)
    if existing is not None:
        return existing, None, False
    if full_text is None:
        return None, NO_FULL_TEXT, False
    if full_text.parse_status != PARSED:
        return None, PARSE_FAILED, False
    return None, None, True


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
    waiting_since = time.monotonic()
    while True:
        existing, unavailable_reason, needs_generation = read_full_text_suggestion(
            db, citation, full_text
        )
        if not needs_generation:
            return existing, unavailable_reason

        # Generating can take seconds. A transaction-scoped advisory lock gives
        # one request the work without blocking the event loop: followers poll
        # for its persisted answer, then retry if that request failed.
        has_generation_lock = db.scalar(
            select(func.pg_try_advisory_xact_lock(func.hashtext(str(citation.id))))
        )
        if not has_generation_lock:
            db.rollback()
            if time.monotonic() - waiting_since >= GENERATION_WAIT_LIMIT_SECONDS:
                return None, GENERATION_FAILED
            await asyncio.sleep(GENERATION_WAIT_SECONDS)
            full_text = crud.get_full_text(db, citation.id)
            continue

        # Re-check after winning the lock: another request might have saved the
        # answer between our first read and acquiring it.
        existing, unavailable_reason, needs_generation = read_full_text_suggestion(
            db, citation, full_text
        )
        if not needs_generation:
            db.rollback()
            return existing, unavailable_reason
        break

    review_project = citation.review_project
    criteria = review_project.criteria
    active_fields = review_project.active_extraction_fields
    # Which version of the PDF the model is about to read, checked again when
    # the answer is saved (see crud.create_full_text_suggestion).
    full_text_stamp = full_text.updated_at

    try:
        result = await asyncio.wait_for(
            suggester.suggest_full_text_decision(
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
            ),
            timeout=GENERATION_TIMEOUT_SECONDS,
        )
    except (SuggestionGenerationError, TimeoutError):
        db.rollback()
        return None, GENERATION_FAILED

    suggestion = crud.create_full_text_suggestion(
        db,
        citation.id,
        decision=result.decision,
        reason=result.reason,
        extraction_values=result.extraction_values,
        active_fields=active_fields,
        full_text_stamp=full_text_stamp,
        model=settings.anthropic_model,
        truncated=result.truncated,
    )
    # None means the PDF was replaced while the model was reading the old one:
    # nothing was saved, and the caller is told neither a suggestion nor a
    # reason, so it looks again.
    return suggestion, None
