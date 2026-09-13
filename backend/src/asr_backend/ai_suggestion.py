from functools import lru_cache
from typing import Any, Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from asr_backend.settings import settings

Decision = Literal["include", "exclude", "maybe"]

_TOOL_NAME = "propose_screening_decision"

_SUGGESTION_TOOL: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": (
        "Propose a screening decision for a citation against a review project's criteria."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["include", "exclude", "maybe"]},
            "reason": {"type": "string"},
        },
        "required": ["decision", "reason"],
        "additionalProperties": False,
    },
    "strict": True,
}

_SYSTEM_PROMPT = (
    "You are a screening assistant for systematic reviews. Given a citation's "
    "title and abstract and a review project's inclusion/exclusion criteria, "
    "propose whether to include, exclude, or mark it as maybe, with a reason "
    "grounded in the given criteria. Apply only the criteria provided; do not "
    "assume criteria that were not stated."
)


class SuggestionResult(BaseModel):
    decision: Decision
    reason: str


class SuggestionGenerationError(Exception):
    """Raised when the Anthropic API call fails or returns an unusable response."""


class AISuggester:
    def __init__(self, client: AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    async def suggest_screening_decision(
        self,
        *,
        title: str,
        abstract: str,
        population: str | None = None,
        intervention: str | None = None,
        comparison: str | None = None,
        outcome: str | None = None,
        exclusion_rules: list[str] | None = None,
        notes: str | None = None,
    ) -> SuggestionResult:
        user_message = _build_user_message(
            title=title,
            abstract=abstract,
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
            exclusion_rules=exclusion_rules or [],
            notes=notes,
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                tools=[_SUGGESTION_TOOL],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            raise SuggestionGenerationError(f"Anthropic API call failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _TOOL_NAME:
                return SuggestionResult.model_validate(block.input)

        raise SuggestionGenerationError("Anthropic response did not include the expected tool call")


def _build_user_message(
    *,
    title: str,
    abstract: str,
    population: str | None,
    intervention: str | None,
    comparison: str | None,
    outcome: str | None,
    exclusion_rules: list[str],
    notes: str | None,
) -> str:
    lines = [f"Title: {title}", f"Abstract: {abstract}", "", "Criteria:"]
    if population:
        lines.append(f"- Population: {population}")
    if intervention:
        lines.append(f"- Intervention: {intervention}")
    if comparison:
        lines.append(f"- Comparison: {comparison}")
    if outcome:
        lines.append(f"- Outcome: {outcome}")
    if exclusion_rules:
        lines.append(f"- Exclusion rules: {', '.join(exclusion_rules)}")
    if notes:
        lines.append(f"- Notes: {notes}")
    return "\n".join(lines)


@lru_cache
def get_ai_suggester() -> AISuggester:
    return AISuggester(
        client=AsyncAnthropic(api_key=settings.anthropic_api_key),
        model=settings.anthropic_model,
    )
