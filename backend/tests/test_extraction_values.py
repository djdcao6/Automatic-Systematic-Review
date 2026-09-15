import io

import pymupdf


def create_project(authed_client, name: str = "My Review") -> str:
    payload = {"name": name, "merge_mode": "combine", "review_mode": "solo"}
    return authed_client.post("/review-projects", json=payload).json()["id"]


def create_citation(authed_client, project_id: str, title: str = "Study A") -> str:
    authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={
            "file": (
                "citations.csv",
                f"title,abstract,authors,year,source\n{title},An abstract,Jane Doe,2020,PubMed\n",
                "text/csv",
            )
        },
    )
    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    return next(c["id"] for c in citations if c["title"] == title)


def create_extraction_field(authed_client, project_id: str, name: str = "Sample size") -> dict:
    return authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": name, "description": None},
    ).json()


def make_pdf(text: str = "Sample paper text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def attach_full_text(authed_client, project_id: str, citation_id: str, content: bytes | None = None):
    return authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": ("paper.pdf", io.BytesIO(content or make_pdf()), "application/pdf")},
    )


def record_extraction_value(authed_client, project_id: str, citation_id: str, field_id: str, value: str):
    return authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}"
        f"/extraction-fields/{field_id}/value",
        json={"value": value},
    )


def get_detail(authed_client, project_id: str, citation_id: str) -> dict:
    return authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()


def test_record_extraction_value(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)
    citation_id = create_citation(authed_client, project_id)

    response = record_extraction_value(
        authed_client, project_id, citation_id, field["id"], "120 participants"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["extraction_field_id"] == field["id"]
    assert body["name"] == "Sample size"
    assert body["value"] == "120 participants"

    detail = get_detail(authed_client, project_id, citation_id)
    assert detail["extraction_values"] == [
        {
            "extraction_field_id": field["id"],
            "name": "Sample size",
            "value": "120 participants",
            "created_at": body["created_at"],
            "updated_at": body["updated_at"],
        }
    ]


def test_extraction_value_is_editable(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)
    citation_id = create_citation(authed_client, project_id)
    record_extraction_value(authed_client, project_id, citation_id, field["id"], "First value")

    response = record_extraction_value(authed_client, project_id, citation_id, field["id"], "Corrected value")

    assert response.status_code == 200
    assert response.json()["value"] == "Corrected value"

    detail = get_detail(authed_client, project_id, citation_id)
    assert len(detail["extraction_values"]) == 1
    assert detail["extraction_values"][0]["value"] == "Corrected value"


def test_extraction_value_can_be_recorded_without_a_full_text(authed_client):
    """A Reviewer can record a value manually when the PDF failed to parse (no AI proposal)."""
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)
    citation_id = create_citation(authed_client, project_id)

    response = record_extraction_value(authed_client, project_id, citation_id, field["id"], "Manual entry")

    assert response.status_code == 200
    assert response.json()["value"] == "Manual entry"


def test_extraction_value_is_stored_separately_from_ai_proposal_even_when_it_matches(authed_client):
    from asr_backend.ai_suggestion import (
        FullTextSuggestionResult,
        SuggestionResult,
        get_ai_suggester,
    )
    from asr_backend.main import app

    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)
    citation_id = create_citation(authed_client, project_id)
    attach_full_text(authed_client, project_id, citation_id)

    class _FakeSuggester:
        async def suggest_screening_decision(self, **kwargs):
            return SuggestionResult(decision="include", reason="Matches criteria.")

        async def suggest_full_text_decision(self, **kwargs):
            return FullTextSuggestionResult(
                decision="include",
                reason="Meets all criteria.",
                extraction_values={field["id"]: "120 participants"},
            )

    app.dependency_overrides[get_ai_suggester] = lambda: _FakeSuggester()
    try:
        detail = get_detail(authed_client, project_id, citation_id)
        proposed_value = detail["full_text_suggestion"]["extraction_values"][0]["value"]
        assert proposed_value == "120 participants"

        record_extraction_value(authed_client, project_id, citation_id, field["id"], proposed_value)

        detail = get_detail(authed_client, project_id, citation_id)
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)

    assert detail["extraction_values"][0]["value"] == "120 participants"
    assert detail["full_text_suggestion"]["extraction_values"][0]["value"] == "120 participants"
    # Two distinct rows exist even though the values match: confirming an
    # AI proposal still records a Reviewer's own Extraction Value.


def test_citation_detail_includes_active_extraction_fields(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id, name="Duration")
    citation_id = create_citation(authed_client, project_id)

    detail = get_detail(authed_client, project_id, citation_id)

    assert detail["extraction_fields"] == [
        {
            "id": field["id"],
            "name": "Duration",
            "description": None,
            "archived": False,
            "created_at": field["created_at"],
            "updated_at": field["updated_at"],
        }
    ]


def test_citation_detail_excludes_archived_extraction_fields(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id, name="Duration")
    citation_id = create_citation(authed_client, project_id)
    authed_client.post(f"/review-projects/{project_id}/extraction-fields/{field['id']}/archive")

    detail = get_detail(authed_client, project_id, citation_id)

    assert detail["extraction_fields"] == []


def test_cannot_record_extraction_value_for_an_archived_field(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)
    citation_id = create_citation(authed_client, project_id)
    authed_client.post(f"/review-projects/{project_id}/extraction-fields/{field['id']}/archive")

    response = record_extraction_value(authed_client, project_id, citation_id, field["id"], "value")

    assert response.status_code == 409


def test_extraction_value_blank_is_rejected(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)
    citation_id = create_citation(authed_client, project_id)

    response = record_extraction_value(authed_client, project_id, citation_id, field["id"], "   ")

    assert response.status_code == 422


def test_record_extraction_value_for_missing_field_returns_404(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    response = record_extraction_value(
        authed_client,
        project_id,
        citation_id,
        "00000000-0000-0000-0000-000000000000",
        "value",
    )

    assert response.status_code == 404


def test_record_extraction_value_for_missing_citation_returns_404(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)

    response = record_extraction_value(
        authed_client,
        project_id,
        "00000000-0000-0000-0000-000000000000",
        field["id"],
        "value",
    )

    assert response.status_code == 404


def test_extraction_values_are_scoped_to_citation(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id)
    citation_a = create_citation(authed_client, project_id, title="Study A")
    citation_b = create_citation(authed_client, project_id, title="Study B")

    record_extraction_value(authed_client, project_id, citation_a, field["id"], "Value A")

    detail_b = get_detail(authed_client, project_id, citation_b)
    assert detail_b["extraction_values"] == []
