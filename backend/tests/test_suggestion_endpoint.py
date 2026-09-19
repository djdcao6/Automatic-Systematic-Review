"""AI Suggestion generation on demand, separate from the citation detail GET (#49)."""

import uuid

import pytest

from asr_backend import models
from asr_backend.ai_suggestion import SuggestionGenerationError, SuggestionResult, get_ai_suggester
from asr_backend.main import app


def create_project(authed_client, name: str = "My Review") -> str:
    payload = {"name": name, "merge_mode": "combine", "review_mode": "solo"}
    return authed_client.post("/review-projects", json=payload).json()["id"]


def upload_one_citation(authed_client, project_id: str, abstract: str | None = "An abstract") -> str:
    csv = "title,abstract,authors,year,source\n" + f"Study,{abstract or ''},Author,2020,PubMed\n"
    authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("c.csv", csv, "text/csv")},
    )
    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
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


def test_post_suggestion_generates_and_returns_the_suggestion(authed_client, override_suggester):
    project_id = create_project(authed_client)
    citation_id = upload_one_citation(authed_client, project_id)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/suggestion"
    )

    assert response.status_code == 200
    assert response.json() == {
        "suggestion": {"decision": "include", "reason": "Matches criteria."},
        "suggestion_unavailable_reason": None,
    }


def test_second_post_returns_the_same_suggestion_without_calling_the_model(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = upload_one_citation(authed_client, project_id)
    url = f"/review-projects/{project_id}/citations/{citation_id}/suggestion"

    first = authed_client.post(url)
    second = authed_client.post(url)

    assert second.json() == first.json()
    assert override_suggester.calls == 1


def test_post_suggestion_for_a_citation_without_an_abstract_skips_the_model(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = upload_one_citation(authed_client, project_id, abstract=None)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/suggestion"
    )

    assert response.status_code == 200
    assert response.json() == {
        "suggestion": None,
        "suggestion_unavailable_reason": "missing_abstract",
    }
    assert override_suggester.calls == 0


def test_failed_generation_is_reported_not_persisted_and_retried_on_the_next_post(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = upload_one_citation(authed_client, project_id)
    citation_url = f"/review-projects/{project_id}/citations/{citation_id}"
    override_suggester.error = SuggestionGenerationError("boom")

    failed = authed_client.post(f"{citation_url}/suggestion")
    detail_after_failure = authed_client.get(citation_url).json()
    override_suggester.error = None
    retried = authed_client.post(f"{citation_url}/suggestion")

    assert failed.status_code == 200
    assert failed.json() == {
        "suggestion": None,
        "suggestion_unavailable_reason": "generation_failed",
    }
    assert detail_after_failure["suggestion_needs_generation"] is True
    assert retried.json()["suggestion"] == {"decision": "include", "reason": "Matches criteria."}


def test_post_that_loses_the_race_to_persist_returns_the_winners_suggestion(authed_client, db_session):
    project_id = create_project(authed_client)
    citation_id = upload_one_citation(authed_client, project_id)
    citation_url = f"/review-projects/{project_id}/citations/{citation_id}"

    class _SuggesterBeatenToPersisting:
        """Another request finishes and saves its suggestion while this one is still generating."""

        async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
            db_session.add(
                models.AISuggestion(
                    citation_id=uuid.UUID(citation_id), decision="exclude", reason="Winner's reason."
                )
            )
            db_session.commit()
            return SuggestionResult(decision="include", reason="Loser's reason.")

    app.dependency_overrides[get_ai_suggester] = lambda: _SuggesterBeatenToPersisting()
    try:
        response = authed_client.post(f"{citation_url}/suggestion")
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)
    detail = authed_client.get(citation_url).json()

    winners = {"decision": "exclude", "reason": "Winner's reason."}
    assert response.status_code == 200
    assert response.json()["suggestion"] == winners
    assert detail["suggestion"] == winners


def test_post_suggestion_for_a_missing_citation_is_not_found(authed_client, override_suggester):
    project_id = create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{uuid.uuid4()}/suggestion"
    )

    assert response.status_code == 404
    assert override_suggester.calls == 0
