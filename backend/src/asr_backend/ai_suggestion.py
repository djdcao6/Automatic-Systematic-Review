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

_FULL_TEXT_TOOL_NAME = "propose_full_text_decision"

_FULL_TEXT_SYSTEM_PROMPT = (
    "You are a full-text review assistant for systematic reviews. Given a "
    "citation's full text and a review project's inclusion/exclusion "
    "criteria, propose whether to include, exclude, or mark it as maybe, "
    "with a reason grounded in the given criteria. Apply only the criteria "
    "provided; do not assume criteria that were not stated. Also propose a "
    "value for each requested extraction field, drawn only from what the "
    "full text actually states."
)


class SuggestionResult(BaseModel):
    decision: Decision
    reason: str


class ExtractionFieldSpec(BaseModel):
    id: str
    name: str
    description: str | None = None


class FullTextSuggestionResult(BaseModel):
    decision: Decision
    reason: str
    extraction_values: dict[str, str] = {}


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

    async def suggest_full_text_decision(
        self,
        *,
        full_text: str,
        extraction_fields: list[ExtractionFieldSpec] | None = None,
        population: str | None = None,
        intervention: str | None = None,
        comparison: str | None = None,
        outcome: str | None = None,
        exclusion_rules: list[str] | None = None,
        notes: str | None = None,
    ) -> FullTextSuggestionResult:
        extraction_fields = extraction_fields or []
        user_message = _build_full_text_user_message(
            full_text=full_text,
            extraction_fields=extraction_fields,
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
            exclusion_rules=exclusion_rules or [],
            notes=notes,
        )
        tool = _build_full_text_tool(extraction_fields)
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_FULL_TEXT_SYSTEM_PROMPT,
                tools=[tool],
                tool_choice={"type": "tool", "name": _FULL_TEXT_TOOL_NAME},
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            raise SuggestionGenerationError(f"Anthropic API call failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _FULL_TEXT_TOOL_NAME:
                return FullTextSuggestionResult.model_validate(block.input)

        raise SuggestionGenerationError("Anthropic response did not include the expected tool call")


def _format_criteria_lines(
    *,
    population: str | None,
    intervention: str | None,
    comparison: str | None,
    outcome: str | None,
    exclusion_rules: list[str],
    notes: str | None,
) -> list[str]:
    lines = []
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
    return lines


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
    lines.extend(
        _format_criteria_lines(
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
            exclusion_rules=exclusion_rules,
            notes=notes,
        )
    )
    return "\n".join(lines)


def _build_full_text_tool(extraction_fields: list[ExtractionFieldSpec]) -> dict[str, Any]:
    # Keyed by field id, not name. Active names are unique per Review Project
    # now (#67), but the id is what stays fixed when a field is renamed, and a
    # name-keyed schema would silently drop a value if two ever collided.
    field_properties = {
        field.id: {
            "type": "string",
            "title": field.name,
            "description": field.description or field.name,
        }
        for field in extraction_fields
    }
    return {
        "name": _FULL_TEXT_TOOL_NAME,
        "description": (
            "Propose a full-text decision for a citation against a review "
            "project's criteria, plus a proposed value for each requested "
            "extraction field."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["include", "exclude", "maybe"]},
                "reason": {"type": "string"},
                "extraction_values": {
                    "type": "object",
                    "properties": field_properties,
                    "required": list(field_properties.keys()),
                    "additionalProperties": False,
                },
            },
            "required": ["decision", "reason", "extraction_values"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _build_full_text_user_message(
    *,
    full_text: str,
    extraction_fields: list[ExtractionFieldSpec],
    population: str | None,
    intervention: str | None,
    comparison: str | None,
    outcome: str | None,
    exclusion_rules: list[str],
    notes: str | None,
) -> str:
    lines = ["Full text:", full_text, "", "Criteria:"]
    lines.extend(
        _format_criteria_lines(
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
            exclusion_rules=exclusion_rules,
            notes=notes,
        )
    )
    if extraction_fields:
        lines.append("")
        lines.append("Extraction fields to propose values for:")
        for field in extraction_fields:
            if field.description:
                lines.append(f"- {field.name}: {field.description}")
            else:
                lines.append(f"- {field.name}")
    return "\n".join(lines)


@lru_cache
def get_ai_suggester() -> AISuggester:
    return AISuggester(
        client=AsyncAnthropic(api_key=settings.anthropic_api_key),
        model=settings.anthropic_model,
    )
