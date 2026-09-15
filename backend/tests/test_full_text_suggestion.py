import io

import pymupdf
import pytest

from asr_backend.ai_suggestion import SuggestionGenerationError, SuggestionResult, get_ai_suggester
from asr_backend.main import app


def create_project(client, name: str = "My Review") -> str:
    payload = {"name": name, "merge_mode": "combine"}
    return client.post("/review-projects", json=payload).json()["id"]


def create_citation(client, project_id: str, title: str = "Study A") -> str:
    client.post(
        f"/review-projects/{project_id}/citations",
        files={
            "file": (
                "citations.csv",
                f"title,abstract,authors,year,source\n{title},An abstract,Jane Doe,2020,PubMed\n",
                "text/csv",
            )
        },
    )
    citations = client.get(f"/review-projects/{project_id}/citations").json()
    return next(c["id"] for c in citations if c["title"] == title)


def create_extraction_field(client, project_id: str, name: str = "Sample size") -> dict:
    return client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": name, "description": None},
    ).json()


def make_pdf(text: str = "Sample paper text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def upload_full_text(client, project_id: str, citation_id: str, content: bytes, filename="paper.pdf"):
    return client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def get_detail(client, project_id: str, citation_id: str) -> dict:
    return client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()


class _FakeSuggester:
    def __init__(
        self,
        decision="include",
        reason="Meets all criteria.",
        extraction_values=None,
        error=None,
    ):
        self.decision = decision
        self.reason = reason
        self.extraction_values = extraction_values or {}
        self.error = error
        self.screening_calls = 0
        self.full_text_calls = 0

    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        self.screening_calls += 1
        return SuggestionResult(decision="include", reason="Matches criteria.")

    async def suggest_full_text_decision(self, **kwargs):
        from asr_backend.ai_suggestion import FullTextSuggestionResult

        self.full_text_calls += 1
        if self.error:
            raise self.error
        return FullTextSuggestionResult(
            decision=self.decision,
            reason=self.reason,
            extraction_values=self.extraction_values,
        )


@pytest.fixture
def override_suggester():
    fake = _FakeSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_suggester, None)


def test_full_text_suggestion_generated_and_persisted_on_first_view(client, override_suggester):
    project_id = create_project(client)
    citation_id = create_citation(client, project_id)
    upload_full_text(client, project_id, citation_id, make_pdf())

    detail = get_detail(client, project_id, citation_id)

    assert detail["full_text_suggestion"]["decision"] == "include"
    assert detail["full_text_suggestion"]["reason"] == "Meets all criteria."
    assert detail["full_text_suggestion_unavailable_reason"] is None
    assert override_suggester.full_text_calls == 1


def test_full_text_suggestion_includes_active_extraction_field_values(client, override_suggester):
    project_id = create_project(client)
    field = create_extraction_field(client, project_id, name="Sample size")
    citation_id = create_citation(client, project_id)
    upload_full_text(client, project_id, citation_id, make_pdf())
    override_suggester.extraction_values = {field["id"]: "120 participants"}

    detail = get_detail(client, project_id, citation_id)

    values = detail["full_text_suggestion"]["extraction_values"]
    assert values == [
        {
            "extraction_field_id": field["id"],
            "name": "Sample size",
            "value": "120 participants",
        }
    ]


def test_full_text_suggestion_keeps_values_distinct_for_same_named_fields(
    client, override_suggester
):
    project_id = create_project(client)
    field_a = create_extraction_field(client, project_id, name="Duration")
    field_b = create_extraction_field(client, project_id, name="Duration")
    citation_id = create_citation(client, project_id)
    upload_full_text(client, project_id, citation_id, make_pdf())
    override_suggester.extraction_values = {
        field_a["id"]: "6 months",
        field_b["id"]: "12 months",
    }

    detail = get_detail(client, project_id, citation_id)

    values = {v["extraction_field_id"]: v["value"] for v in detail["full_text_suggestion"]["extraction_values"]}
    assert values == {field_a["id"]: "6 months", field_b["id"]: "12 months"}


def test_full_text_suggestion_is_reused_on_second_view(client, override_suggester):
    project_id = create_project(client)
    citation_id = create_citation(client, project_id)
    upload_full_text(client, project_id, citation_id, make_pdf())

    get_detail(client, project_id, citation_id)
    get_detail(client, project_id, citation_id)

    assert override_suggester.full_text_calls == 1


def test_full_text_suggestion_unavailable_without_a_full_text(client, override_suggester):
    project_id = create_project(client)
    citation_id = create_citation(client, project_id)

    detail = get_detail(client, project_id, citation_id)

    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_unavailable_reason"] == "no_full_text"
    assert override_suggester.full_text_calls == 0


def test_full_text_suggestion_unavailable_when_parse_failed(client, override_suggester):
    project_id = create_project(client)
    citation_id = create_citation(client, project_id)
    # An all-image PDF page has no extractable text layer, so parsing fails.
    doc = pymupdf.open()
    doc.new_page()
    upload_full_text(client, project_id, citation_id, doc.tobytes())

    detail = get_detail(client, project_id, citation_id)

    assert detail["full_text"]["parse_status"] == "parse_failed"
    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_unavailable_reason"] == "parse_failed"
    assert override_suggester.full_text_calls == 0


def test_full_text_suggestion_generation_failure_reports_reason(client):
    project_id = create_project(client)
    citation_id = create_citation(client, project_id)
    upload_full_text(client, project_id, citation_id, make_pdf())
    app.dependency_overrides[get_ai_suggester] = lambda: _FakeSuggester(
        error=SuggestionGenerationError("boom")
    )

    detail = get_detail(client, project_id, citation_id)
    app.dependency_overrides.pop(get_ai_suggester, None)

    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_unavailable_reason"] == "generation_failed"


def test_replacing_the_pdf_invalidates_and_regenerates_the_suggestion(client, override_suggester):
    project_id = create_project(client)
    citation_id = create_citation(client, project_id)
    upload_full_text(client, project_id, citation_id, make_pdf("First version"))
    get_detail(client, project_id, citation_id)
    assert override_suggester.full_text_calls == 1

    override_suggester.decision = "exclude"
    override_suggester.reason = "Wrong study design after re-read."
    upload_full_text(client, project_id, citation_id, make_pdf("Second version"))

    detail = get_detail(client, project_id, citation_id)

    assert override_suggester.full_text_calls == 2
    assert detail["full_text_suggestion"]["decision"] == "exclude"
    assert detail["full_text_suggestion"]["reason"] == "Wrong study design after re-read."


def test_full_text_suggestion_for_missing_citation_returns_404(client, override_suggester):
    project_id = create_project(client)

    response = client.get(
        f"/review-projects/{project_id}/citations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404
