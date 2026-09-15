import pytest

from asr_backend.ai_suggestion import SuggestionGenerationError, SuggestionResult, get_ai_suggester
from asr_backend.main import app


def create_project(client, name: str = "My Review") -> str:
    payload = {"name": name, "merge_mode": "combine"}
    return client.post("/review-projects", json=payload).json()["id"]


def upload_one_citation(client, project_id: str, abstract: str | None = "An abstract") -> str:
    csv = "title,abstract,authors,year,source\n" + f"Study,{abstract or ''},Author,2020,PubMed\n"
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("c.csv", csv, "text/csv")},
    )
    citations = client.get(f"/review-projects/{project_id}/citations").json()
    return citations[-1]["id"]


class _FakeSuggester:
    def __init__(self, decision="include", reason="Matches criteria.", error=None):
        self.decision = decision
        self.reason = reason
        self.error = error
        self.calls = 0

    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        self.calls += 1
        if self.error:
            raise self.error
        return SuggestionResult(decision=self.decision, reason=self.reason)


@pytest.fixture
def override_suggester():
    fake = _FakeSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_suggester, None)


def test_citation_detail_generates_and_persists_suggestion(client, override_suggester):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id)

    response = client.get(f"/review-projects/{project_id}/citations/{citation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"] == {"decision": "include", "reason": "Matches criteria."}
    assert body["suggestion_unavailable_reason"] is None
    assert override_suggester.calls == 1


def test_citation_detail_reuses_persisted_suggestion_on_second_view(client, override_suggester):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id)

    client.get(f"/review-projects/{project_id}/citations/{citation_id}")
    response = client.get(f"/review-projects/{project_id}/citations/{citation_id}")

    assert response.json()["suggestion"] == {"decision": "include", "reason": "Matches criteria."}
    assert override_suggester.calls == 1


def test_citation_detail_missing_abstract_skips_generation(client, override_suggester):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id, abstract=None)

    response = client.get(f"/review-projects/{project_id}/citations/{citation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"] is None
    assert body["suggestion_unavailable_reason"] == "missing_abstract"
    assert override_suggester.calls == 0


def test_citation_detail_generation_failure_reports_reason(client):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id)
    app.dependency_overrides[get_ai_suggester] = lambda: _FakeSuggester(
        error=SuggestionGenerationError("boom")
    )

    response = client.get(f"/review-projects/{project_id}/citations/{citation_id}")
    app.dependency_overrides.pop(get_ai_suggester, None)

    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"] is None
    assert body["suggestion_unavailable_reason"] == "generation_failed"


def test_citation_detail_for_missing_citation(client, override_suggester):
    project_id = create_project(client)

    response = client.get(
        f"/review-projects/{project_id}/citations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


def test_citation_detail_for_missing_review_project(client, override_suggester):
    response = client.get(
        "/review-projects/00000000-0000-0000-0000-000000000000/citations/"
        "00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


def test_record_screening_decision(client, override_suggester):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id)

    response = client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "include", "reason": "Good fit"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "include"
    assert body["reason"] == "Good fit"


def test_recording_decision_locks_criteria(client, override_suggester):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id)

    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "exclude"},
    )

    project = client.get(f"/review-projects/{project_id}").json()
    assert project["criteria_locked"] is True

    edit_response = client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Adults"},
    )
    assert edit_response.status_code == 409


def test_criteria_editable_before_any_decision(client, override_suggester):
    project_id = create_project(client)

    response = client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Adults"},
    )

    assert response.status_code == 200


def test_decision_is_editable_after_recording(client, override_suggester):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id)

    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "maybe"},
    )
    response = client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "include", "reason": "Changed my mind"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "include"
    assert body["reason"] == "Changed my mind"


def test_review_project_shows_live_undecided_count(client, override_suggester):
    project_id = create_project(client)
    citation_id = upload_one_citation(client, project_id)
    second_csv = "title,abstract,authors,year,source\nSecond,Abstract,Author,2020,PubMed\n"
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("c2.csv", second_csv, "text/csv")},
    )

    project = client.get(f"/review-projects/{project_id}").json()
    assert project["citations_needing_decision"] == 2

    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "include"},
    )

    project = client.get(f"/review-projects/{project_id}").json()
    assert project["citations_needing_decision"] == 1
