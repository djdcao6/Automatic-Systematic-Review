"""Independent per-reviewer Screening Decisions with blinding (#27)."""

import pytest
from conftest import auth_headers_for

from asr_backend.ai_suggestion import SuggestionResult, get_ai_suggester
from asr_backend.main import app

CSV_SAMPLE = "title,abstract,authors,year,source\nStudy,An abstract,Author,2020,PubMed\n"


def _create_dual_project(client, headers, name: str = "Dual Review") -> str:
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "dual"},
        headers=headers,
    ).json()["id"]


def _create_solo_project(client, headers, name: str = "Solo Review") -> str:
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
        headers=headers,
    ).json()["id"]


def _upload_one_citation(client, headers, project_id: str) -> str:
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", CSV_SAMPLE, "text/csv")},
        headers=headers,
    )
    citations = client.get(f"/review-projects/{project_id}/citations", headers=headers).json()
    return citations[-1]["id"]


def _add_co_reviewer(client, owner_headers, project_id: str, email: str = "co-reviewer@example.com"):
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    access_token = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": email, "password": "correcthorse"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


class _FakeSuggester:
    def __init__(self, decision="include", reason="Matches criteria."):
        self.decision = decision
        self.reason = reason
        self.calls = 0

    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        self.calls += 1
        return SuggestionResult(decision=self.decision, reason=self.reason)


@pytest.fixture
def override_suggester():
    fake = _FakeSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_suggester, None)


@pytest.fixture
def dual_setup(client, override_suggester):
    """A Dual Review Project with one Citation, an accepted Co-Reviewer, and headers for both."""
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    co_reviewer_headers = _add_co_reviewer(client, owner_headers, project_id)
    citation_id = _upload_one_citation(client, owner_headers, project_id)
    return {
        "project_id": project_id,
        "citation_id": citation_id,
        "owner_headers": owner_headers,
        "co_reviewer_headers": co_reviewer_headers,
    }


def _get_citation(client, project_id, citation_id, headers):
    return client.get(
        f"/review-projects/{project_id}/citations/{citation_id}", headers=headers
    ).json()


def _record_decision(client, project_id, citation_id, headers, decision, reason=None):
    return client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": decision, "reason": reason},
        headers=headers,
    ).json()


# --- Blinding ---


def test_reviewer_who_has_not_decided_is_blind_to_suggestion_and_peer(client, dual_setup):
    d = dual_setup
    _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude", "Wrong population"
    )

    body = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])

    assert body["screening_blind"] is True
    assert body["suggestion"] is None
    assert body["suggestion_unavailable_reason"] is None
    assert body["screening_decision"] is None
    assert body["peer_screening_decision"] is None


def test_first_opener_is_blind_even_when_no_one_has_decided_yet(client, dual_setup):
    """Per ADR 0006: the first Reviewer to open a Citation gets no exception."""
    d = dual_setup

    body = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])

    assert body["screening_blind"] is True
    assert body["suggestion"] is None
    assert body["screening_decision"] is None
    assert body["peer_screening_decision"] is None


def test_recording_own_decision_reveals_suggestion(client, dual_setup):
    d = dual_setup

    body = _record_decision(
        client, d["project_id"], d["citation_id"], d["owner_headers"], "include", "Looks relevant"
    )
    assert body["decision"] == "include"

    detail = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])
    assert detail["screening_blind"] is False
    assert detail["suggestion"] == {"decision": "include", "reason": "Matches criteria."}
    assert detail["screening_decision"]["decision"] == "include"
    assert detail["screening_decision"]["reason"] == "Looks relevant"


def test_revealed_view_shows_peer_decision_once_both_have_recorded(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude", "Wrong population"
    )

    owner_view = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])
    co_reviewer_view = _get_citation(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"])

    assert owner_view["screening_decision"]["decision"] == "include"
    assert owner_view["peer_screening_decision"]["decision"] == "exclude"
    assert owner_view["peer_screening_decision"]["reason"] == "Wrong population"

    assert co_reviewer_view["screening_decision"]["decision"] == "exclude"
    assert co_reviewer_view["peer_screening_decision"]["decision"] == "include"


def test_revealed_before_peer_decides_shows_own_decision_and_no_peer_yet(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")

    detail = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])

    assert detail["screening_blind"] is False
    assert detail["screening_decision"]["decision"] == "include"
    assert detail["peer_screening_decision"] is None
    assert detail["suggestion"] is not None


def test_suggestion_is_generated_once_regardless_of_when_it_is_revealed(client, dual_setup, override_suggester):
    d = dual_setup

    _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])
    _get_citation(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"])
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    revealed = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])

    assert revealed["suggestion"] == {"decision": "include", "reason": "Matches criteria."}
    assert override_suggester.calls == 1


# --- Independent recording ---


def test_owner_and_co_reviewer_record_independent_decisions(client, dual_setup):
    d = dual_setup

    owner_result = _record_decision(
        client, d["project_id"], d["citation_id"], d["owner_headers"], "include", "Owner's take"
    )
    co_reviewer_result = _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude", "Co-Reviewer's take"
    )

    assert owner_result["decision"] == "include"
    assert co_reviewer_result["decision"] == "exclude"

    owner_view = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])
    assert owner_view["screening_decision"]["decision"] == "include"
    assert owner_view["screening_decision"]["reason"] == "Owner's take"


def test_editing_own_decision_does_not_affect_peer_decision(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")

    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "maybe", "Reconsidering")

    owner_view = _get_citation(client, d["project_id"], d["citation_id"], d["owner_headers"])
    assert owner_view["screening_decision"]["decision"] == "maybe"
    assert owner_view["peer_screening_decision"]["decision"] == "exclude"


# --- Solo unaffected ---


def test_solo_project_screening_view_is_unchanged(client, override_suggester):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_solo_project(client, owner_headers)
    citation_id = _upload_one_citation(client, owner_headers, project_id)

    body = _get_citation(client, project_id, citation_id, owner_headers)

    assert body["screening_blind"] is False
    assert body["suggestion"] == {"decision": "include", "reason": "Matches criteria."}
    assert body["peer_screening_decision"] is None


# --- Needs-decision status ---


def test_needs_decision_reflects_either_reviewer_not_having_decided(client, dual_setup):
    d = dual_setup

    project = client.get(f"/review-projects/{d['project_id']}", headers=d["owner_headers"]).json()
    assert project["citations_needing_decision"] == 1

    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    project = client.get(f"/review-projects/{d['project_id']}", headers=d["owner_headers"]).json()
    assert project["citations_needing_decision"] == 1

    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    project = client.get(f"/review-projects/{d['project_id']}", headers=d["owner_headers"]).json()
    assert project["citations_needing_decision"] == 0


def test_needs_decision_before_co_reviewer_has_joined_reflects_owner_alone(client, override_suggester):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    citation_id = _upload_one_citation(client, owner_headers, project_id)

    project = client.get(f"/review-projects/{project_id}", headers=owner_headers).json()
    assert project["citations_needing_decision"] == 1

    _record_decision(client, project_id, citation_id, owner_headers, "include")

    project = client.get(f"/review-projects/{project_id}", headers=owner_headers).json()
    assert project["citations_needing_decision"] == 0
