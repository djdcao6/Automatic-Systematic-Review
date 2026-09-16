from functools import lru_cache
from typing import Any

from anthropic import AsyncAnthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from asr_backend import crud, models, schemas
from asr_backend.ai_suggestion import _format_criteria_lines
from asr_backend.settings import settings

_TOOL_NAME = "propose_search_terms"

_SEARCH_TERMS_TOOL: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": (
        "Propose database search terms for a systematic review, one list of "
        "synonyms/related terms per populated PICO concept."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "population_terms": {"type": "array", "items": {"type": "string"}},
            "intervention_terms": {"type": "array", "items": {"type": "string"}},
            "comparison_terms": {"type": "array", "items": {"type": "string"}},
            "outcome_terms": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "population_terms",
            "intervention_terms",
            "comparison_terms",
            "outcome_terms",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}

_SYSTEM_PROMPT = (
    "You are a search strategy assistant for systematic reviews. Given a "
    "review project's PICO criteria, propose a list of database search terms "
    "(synonyms and closely related terms) for each populated PICO field. "
    "Return an empty list for any field that was not provided. Ground every "
    "term in the given criteria; do not invent concepts that were not stated."
)


class SearchTermsResult(BaseModel):
    population_terms: list[str] = []
    intervention_terms: list[str] = []
    comparison_terms: list[str] = []
    outcome_terms: list[str] = []


class SearchTermsGenerationError(Exception):
    """Raised when the Anthropic API call fails or returns an unusable response."""


class NoPicoFieldPopulatedError(Exception):
    """Raised when generation is requested but no PICO field is populated."""


class SearchTermsGenerator:
    def __init__(self, client: AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(
        self,
        *,
        population: str | None = None,
        intervention: str | None = None,
        comparison: str | None = None,
        outcome: str | None = None,
    ) -> SearchTermsResult:
        if not any([population, intervention, comparison, outcome]):
            raise NoPicoFieldPopulatedError(
                "At least one PICO field must be populated to generate Search Terms"
            )
        user_message = _build_user_message(
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=[_SEARCH_TERMS_TOOL],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            raise SearchTermsGenerationError(f"Anthropic API call failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _TOOL_NAME:
                return SearchTermsResult.model_validate(block.input)

        raise SearchTermsGenerationError(
            "Anthropic response did not include the expected tool call"
        )


def _build_user_message(
    *,
    population: str | None,
    intervention: str | None,
    comparison: str | None,
    outcome: str | None,
) -> str:
    lines = ["Criteria:"]
    lines.extend(
        _format_criteria_lines(
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
            # Search Terms generation is PICO-only by design (see CONTEXT.md's
            # Search Terms entry) — exclusion rules/notes are deliberately
            # never surfaced here, not an oversight.
            exclusion_rules=[],
            notes=None,
        )
    )
    return "\n".join(lines)


async def generate_and_persist(
    db: Session,
    project: models.ReviewProject,
    generator: SearchTermsGenerator,
) -> models.SearchTerms:
    """Generates Search Terms from the project's Criteria and persists them.

    Always calls the Anthropic API and overwrites any previously stored
    Search Terms (#36) — unlike the AI Suggestion pattern (asr_backend.
    screening), which generates lazily once and reuses the result, this is
    an explicit user-triggered "generate" action with no cached-reuse path.
    """
    criteria = project.criteria
    result = await generator.generate(
        population=criteria.population if criteria else None,
        intervention=criteria.intervention if criteria else None,
        comparison=criteria.comparison if criteria else None,
        outcome=criteria.outcome if criteria else None,
    )
    payload = schemas.SearchTermsUpdate(
        population_terms=result.population_terms,
        intervention_terms=result.intervention_terms,
        comparison_terms=result.comparison_terms,
        outcome_terms=result.outcome_terms,
    )
    return crud.upsert_search_terms(db, project, payload)


def compute_combined_query(search_terms: models.SearchTerms) -> str:
    """Derives the combined boolean query string from the stored term lists.

    Concept terms are OR'd together, and populated concepts are AND'd across
    each other; a concept with no terms contributes no clause. Never stored
    (#36) so it can't drift from the term lists after an edit.
    """
    concept_clauses = [
        "(" + " OR ".join(terms) + ")"
        for terms in (
            search_terms.population_terms,
            search_terms.intervention_terms,
            search_terms.comparison_terms,
            search_terms.outcome_terms,
        )
        if terms
    ]
    return " AND ".join(concept_clauses)


def to_read_schema(search_terms: models.SearchTerms) -> schemas.SearchTermsRead:
    return schemas.SearchTermsRead(
        population_terms=search_terms.population_terms,
        intervention_terms=search_terms.intervention_terms,
        comparison_terms=search_terms.comparison_terms,
        outcome_terms=search_terms.outcome_terms,
        combined_query=compute_combined_query(search_terms),
    )


@lru_cache
def get_search_terms_generator() -> SearchTermsGenerator:
    return SearchTermsGenerator(
        client=AsyncAnthropic(api_key=settings.anthropic_api_key),
        model=settings.anthropic_model,
    )
