"""Conflict detection & resolution (#28)."""

import pytest
from conftest import auth_headers_for

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


@pytest.fixture
def dual_setup(client):
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


def _record_decision(client, project_id, citation_id, headers, decision, reason=None):
    return client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": decision, "reason": reason},
        headers=headers,
    ).json()


def _list_conflicts(client, project_id, headers):
    response = client.get(f"/review-projects/{project_id}/conflicts", headers=headers)
    assert response.status_code == 200
    return response.json()


def _resolve_conflict(client, project_id, conflict_id, headers, decision, reason=None):
    return client.post(
        f"/review-projects/{project_id}/conflicts/{conflict_id}/resolve",
        json={"decision": decision, "reason": reason},
        headers=headers,
    )


def _export_rows(client, project_id, headers):
    response = client.get(f"/review-projects/{project_id}/export", headers=headers)
    lines = [line for line in response.text.splitlines() if line and not line.startswith("#")]
    header, *rows = lines
    return header.split(","), [row.split(",") for row in rows]


# --- Detection ---


def test_no_conflict_while_only_one_reviewer_has_decided(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")

    assert _list_conflicts(client, d["project_id"], d["owner_headers"]) == []


def test_no_conflict_when_both_reviewers_agree(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "include")

    assert _list_conflicts(client, d["project_id"], d["owner_headers"]) == []


def test_conflict_created_when_both_reviewers_disagree(client, dual_setup):
    d = dual_setup
    _record_decision(
        client, d["project_id"], d["citation_id"], d["owner_headers"], "include", "Owner's take"
    )
    _record_decision(
        client,
        d["project_id"],
        d["citation_id"],
        d["co_reviewer_headers"],
        "exclude",
        "Co-Reviewer's take",
    )

    conflicts = _list_conflicts(client, d["project_id"], d["owner_headers"])
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["citation"]["id"] == d["citation_id"]
    assert conflict["owner_decision"] == {
        "decision": "include",
        "reason": "Owner's take",
        "created_at": conflict["owner_decision"]["created_at"],
        "updated_at": conflict["owner_decision"]["updated_at"],
    }
    assert conflict["co_reviewer_decision"]["decision"] == "exclude"
    assert conflict["co_reviewer_decision"]["reason"] == "Co-Reviewer's take"


def test_pending_conflict_clears_when_an_edit_brings_decisions_back_into_agreement(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    assert len(_list_conflicts(client, d["project_id"], d["owner_headers"])) == 1

    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "exclude")

    assert _list_conflicts(client, d["project_id"], d["owner_headers"]) == []


def test_resolved_conflict_is_not_reopened_by_a_later_edit(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]
    _resolve_conflict(client, d["project_id"], conflict_id, d["owner_headers"], "maybe")

    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "maybe")

    assert _list_conflicts(client, d["project_id"], d["owner_headers"]) == []


def test_no_conflict_in_solo_project(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_solo_project(client, owner_headers)
    citation_id = _upload_one_citation(client, owner_headers, project_id)
    _record_decision(client, project_id, citation_id, owner_headers, "include")

    assert _list_conflicts(client, project_id, owner_headers) == []


def test_conflict_list_excludes_resolved_conflicts(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]

    _resolve_conflict(client, d["project_id"], conflict_id, d["owner_headers"], "include")

    assert _list_conflicts(client, d["project_id"], d["owner_headers"]) == []


# --- Resolution ---


def test_owner_resolves_by_picking_owner_side(client, dual_setup):
    d = dual_setup
    _record_decision(
        client, d["project_id"], d["citation_id"], d["owner_headers"], "include", "Owner's take"
    )
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]

    response = _resolve_conflict(
        client, d["project_id"], conflict_id, d["owner_headers"], "include", "Owner's take"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolved_decision"] == "include"
    assert body["resolved_reason"] == "Owner's take"


def test_owner_resolves_by_picking_co_reviewer_side(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(
        client,
        d["project_id"],
        d["citation_id"],
        d["co_reviewer_headers"],
        "exclude",
        "Wrong population",
    )
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]

    response = _resolve_conflict(
        client, d["project_id"], conflict_id, d["owner_headers"], "exclude", "Wrong population"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resolved_decision"] == "exclude"
    assert body["resolved_reason"] == "Wrong population"


def test_owner_resolves_with_a_fresh_decision(client, dual_setup):
    """Per ADR 0006: resolution isn't constrained to either original value."""
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]

    response = _resolve_conflict(
        client,
        d["project_id"],
        conflict_id,
        d["owner_headers"],
        "maybe",
        "Discussed together; needs full text",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resolved_decision"] == "maybe"
    assert body["resolved_reason"] == "Discussed together; needs full text"


def test_both_original_decisions_remain_after_resolution(client, dual_setup):
    d = dual_setup
    _record_decision(
        client, d["project_id"], d["citation_id"], d["owner_headers"], "include", "Owner's take"
    )
    _record_decision(
        client,
        d["project_id"],
        d["citation_id"],
        d["co_reviewer_headers"],
        "exclude",
        "Co-Reviewer's take",
    )
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]
    _resolve_conflict(client, d["project_id"], conflict_id, d["owner_headers"], "maybe", "Fresh call")

    owner_view = client.get(
        f"/review-projects/{d['project_id']}/citations/{d['citation_id']}",
        headers=d["owner_headers"],
    ).json()
    assert owner_view["screening_decision"]["decision"] == "include"
    assert owner_view["screening_decision"]["reason"] == "Owner's take"
    assert owner_view["peer_screening_decision"]["decision"] == "exclude"
    assert owner_view["peer_screening_decision"]["reason"] == "Co-Reviewer's take"


def test_non_owner_cannot_resolve_conflict(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]

    response = _resolve_conflict(
        client, d["project_id"], conflict_id, d["co_reviewer_headers"], "include"
    )

    assert response.status_code == 403


def test_resolving_an_already_resolved_conflict_fails(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]
    _resolve_conflict(client, d["project_id"], conflict_id, d["owner_headers"], "include")

    response = _resolve_conflict(client, d["project_id"], conflict_id, d["owner_headers"], "exclude")

    assert response.status_code == 409


def test_resolving_missing_conflict_returns_404(client, dual_setup):
    d = dual_setup

    response = _resolve_conflict(
        client, d["project_id"], "00000000-0000-0000-0000-000000000000", d["owner_headers"], "include"
    )

    assert response.status_code == 404


# --- Effective decision ---


def test_screening_not_resolved_while_conflict_pending(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")

    owner_view = client.get(
        f"/review-projects/{d['project_id']}/citations/{d['citation_id']}",
        headers=d["owner_headers"],
    ).json()
    assert owner_view["screening_resolved"] is False


def test_screening_resolved_after_conflict_resolution(client, dual_setup):
    d = dual_setup
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude")
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]
    _resolve_conflict(client, d["project_id"], conflict_id, d["owner_headers"], "exclude")

    owner_view = client.get(
        f"/review-projects/{d['project_id']}/citations/{d['citation_id']}",
        headers=d["owner_headers"],
    ).json()
    assert owner_view["screening_resolved"] is True


def test_export_reflects_resolved_conflict_decision(client, dual_setup):
    d = dual_setup
    _record_decision(
        client, d["project_id"], d["citation_id"], d["owner_headers"], "include", "Owner's take"
    )
    _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude"
    )
    conflict_id = _list_conflicts(client, d["project_id"], d["owner_headers"])[0]["id"]
    _resolve_conflict(
        client, d["project_id"], conflict_id, d["owner_headers"], "maybe", "Needs full text"
    )

    header, rows = _export_rows(client, d["project_id"], d["owner_headers"])
    decision_index = header.index("screening_decision")
    reason_index = header.index("reason")
    assert rows[0][decision_index] == "maybe"
    assert rows[0][reason_index] == "Needs full text"


def test_export_unaffected_when_no_conflict_exists(client, dual_setup):
    d = dual_setup
    _record_decision(
        client, d["project_id"], d["citation_id"], d["owner_headers"], "include", "Owner's take"
    )

    header, rows = _export_rows(client, d["project_id"], d["owner_headers"])
    decision_index = header.index("screening_decision")
    assert rows[0][decision_index] == "include"
