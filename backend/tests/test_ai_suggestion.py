import asyncio
from types import SimpleNamespace

import pytest

from asr_backend.ai_suggestion import (
    AISuggester,
    ExtractionFieldSpec,
    SuggestionGenerationError,
    _build_full_text_user_message,
    _build_user_message,
    _format_criteria_lines,
)


def _tool_response(decision: str, reason: str) -> SimpleNamespace:
    block = SimpleNamespace(
        type="tool_use",
        name="propose_screening_decision",
        input={"decision": decision, "reason": reason},
    )
    return SimpleNamespace(content=[block])


class _FakeMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.messages = _FakeMessages(response=response, error=error)


def test_suggest_screening_decision_returns_parsed_result():
    client = _FakeClient(response=_tool_response("include", "Matches the population."))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    result = asyncio.run(
        suggester.suggest_screening_decision(
            title="A trial of metformin",
            abstract="Adults with type 2 diabetes...",
            population="Adults with type 2 diabetes",
        )
    )

    assert result.decision == "include"
    assert result.reason == "Matches the population."


def test_suggest_screening_decision_raises_on_api_error():
    client = _FakeClient(error=RuntimeError("boom"))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    with pytest.raises(SuggestionGenerationError):
        asyncio.run(
            suggester.suggest_screening_decision(title="Title", abstract="Abstract")
        )


def test_suggest_screening_decision_raises_when_no_tool_call_returned():
    client = _FakeClient(response=SimpleNamespace(content=[]))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    with pytest.raises(SuggestionGenerationError):
        asyncio.run(
            suggester.suggest_screening_decision(title="Title", abstract="Abstract")
        )


def test_suggest_screening_decision_forces_the_tool_call():
    client = _FakeClient(response=_tool_response("exclude", "Wrong population."))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    asyncio.run(suggester.suggest_screening_decision(title="Title", abstract="Abstract"))

    assert client.messages.last_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "propose_screening_decision",
    }


def test_user_message_omits_blank_criteria_fields():
    message = _build_user_message(
        title="Title",
        abstract="Abstract",
        population=None,
        intervention=None,
        comparison=None,
        outcome=None,
        exclusion_rules=[],
        notes=None,
    )

    assert "Population" not in message
    assert "Intervention" not in message
    assert "Exclusion rules" not in message


def test_user_message_includes_only_populated_criteria_fields():
    message = _build_user_message(
        title="Title",
        abstract="Abstract",
        population="Adults",
        intervention=None,
        comparison=None,
        outcome="HbA1c reduction",
        exclusion_rules=["Animal studies"],
        notes=None,
    )

    assert "- Population: Adults" in message
    assert "- Outcome: HbA1c reduction" in message
    assert "- Exclusion rules: Animal studies" in message
    assert "Intervention" not in message
    assert "Notes" not in message


def test_format_criteria_lines_returns_nothing_when_all_fields_blank():
    lines = _format_criteria_lines(
        population=None,
        intervention=None,
        comparison=None,
        outcome=None,
        exclusion_rules=[],
        notes=None,
    )

    assert lines == []


def test_format_criteria_lines_includes_every_populated_field_in_order():
    lines = _format_criteria_lines(
        population="Adults",
        intervention="Metformin",
        comparison="Placebo",
        outcome="HbA1c reduction",
        exclusion_rules=["Animal studies", "Non-English"],
        notes="Prefer RCTs",
    )

    assert lines == [
        "- Population: Adults",
        "- Intervention: Metformin",
        "- Comparison: Placebo",
        "- Outcome: HbA1c reduction",
        "- Exclusion rules: Animal studies, Non-English",
        "- Notes: Prefer RCTs",
    ]


def test_format_criteria_lines_skips_blank_fields_individually():
    lines = _format_criteria_lines(
        population="Adults",
        intervention=None,
        comparison=None,
        outcome="HbA1c reduction",
        exclusion_rules=[],
        notes=None,
    )

    assert lines == ["- Population: Adults", "- Outcome: HbA1c reduction"]


def _full_text_tool_response(decision: str, reason: str, extraction_values: dict) -> SimpleNamespace:
    block = SimpleNamespace(
        type="tool_use",
        name="propose_full_text_decision",
        input={"decision": decision, "reason": reason, "extraction_values": extraction_values},
    )
    return SimpleNamespace(content=[block])


def test_suggest_full_text_decision_returns_parsed_result_with_extraction_values():
    client = _FakeClient(
        response=_full_text_tool_response(
            "include", "Meets all criteria.", {"field-1": "120 participants"}
        )
    )
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    result = asyncio.run(
        suggester.suggest_full_text_decision(
            full_text="This trial enrolled 120 participants...",
            extraction_fields=[ExtractionFieldSpec(id="field-1", name="Sample size")],
        )
    )

    assert result.decision == "include"
    assert result.reason == "Meets all criteria."
    assert result.extraction_values == {"field-1": "120 participants"}


def test_suggest_full_text_decision_raises_on_api_error():
    client = _FakeClient(error=RuntimeError("boom"))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    with pytest.raises(SuggestionGenerationError):
        asyncio.run(suggester.suggest_full_text_decision(full_text="Full text"))


def test_suggest_full_text_decision_raises_when_no_tool_call_returned():
    client = _FakeClient(response=SimpleNamespace(content=[]))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    with pytest.raises(SuggestionGenerationError):
        asyncio.run(suggester.suggest_full_text_decision(full_text="Full text"))


def test_suggest_full_text_decision_forces_the_tool_call():
    client = _FakeClient(response=_full_text_tool_response("exclude", "Wrong design.", {}))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    asyncio.run(suggester.suggest_full_text_decision(full_text="Full text"))

    assert client.messages.last_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "propose_full_text_decision",
    }


def test_suggest_full_text_decision_builds_tool_schema_from_extraction_fields():
    client = _FakeClient(response=_full_text_tool_response("maybe", "Unclear.", {}))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    asyncio.run(
        suggester.suggest_full_text_decision(
            full_text="Full text",
            extraction_fields=[
                ExtractionFieldSpec(id="field-1", name="Sample size", description="Number enrolled"),
                ExtractionFieldSpec(id="field-2", name="Methodology"),
            ],
        )
    )

    tool = client.messages.last_kwargs["tools"][0]
    properties = tool["input_schema"]["properties"]["extraction_values"]["properties"]
    assert properties["field-1"] == {
        "type": "string",
        "title": "Sample size",
        "description": "Number enrolled",
    }
    assert properties["field-2"] == {
        "type": "string",
        "title": "Methodology",
        "description": "Methodology",
    }


def test_suggest_full_text_decision_keeps_same_named_fields_distinct():
    """Two active Extraction Fields can share a name; each must still get its own tool property."""
    client = _FakeClient(response=_full_text_tool_response("maybe", "Unclear.", {}))
    suggester = AISuggester(client=client, model="claude-haiku-4-5")

    asyncio.run(
        suggester.suggest_full_text_decision(
            full_text="Full text",
            extraction_fields=[
                ExtractionFieldSpec(id="field-1", name="Duration"),
                ExtractionFieldSpec(id="field-2", name="Duration"),
            ],
        )
    )

    tool = client.messages.last_kwargs["tools"][0]
    properties = tool["input_schema"]["properties"]["extraction_values"]["properties"]
    assert set(properties.keys()) == {"field-1", "field-2"}


def test_full_text_user_message_includes_full_text_and_extraction_fields():
    message = _build_full_text_user_message(
        full_text="The study enrolled 50 adults.",
        extraction_fields=[
            ExtractionFieldSpec(id="field-1", name="Sample size", description="Number enrolled")
        ],
        population="Adults",
        intervention=None,
        comparison=None,
        outcome=None,
        exclusion_rules=[],
        notes=None,
    )

    assert "The study enrolled 50 adults." in message
    assert "- Population: Adults" in message
    assert "- Sample size: Number enrolled" in message
