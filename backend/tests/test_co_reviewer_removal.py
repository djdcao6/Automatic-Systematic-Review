"""Remove & replace a Co-Reviewer (#29)."""

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


def _record_decision(client, project_id, citation_id, headers, decision, reason=None):
    return client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": decision, "reason": reason},
        headers=headers,
    ).json()


def _remove_co_reviewer(client, project_id, headers):
    return client.post(
        f"/review-projects/{project_id}/co-reviewer/remove", headers=headers
    )


def _dual_setup(client, override_suggester=None):
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


# --- Removal ---


def test_owner_can_remove_co_reviewer(client):
    d = _dual_setup(client)

    response = _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    assert response.status_code == 200
    body = response.json()
    assert body["co_reviewer_id"] is None
    assert body["review_mode"] == "dual"


def test_non_owner_cannot_remove_co_reviewer(client):
    d = _dual_setup(client)

    response = _remove_co_reviewer(client, d["project_id"], d["co_reviewer_headers"])

    assert response.status_code == 403


def test_unrelated_reviewer_cannot_remove_co_reviewer(client):
    d = _dual_setup(client)
    other_headers = auth_headers_for(client, "someone-else@example.com")

    response = _remove_co_reviewer(client, d["project_id"], other_headers)

    assert response.status_code == 403


def test_cannot_remove_co_reviewer_when_none_has_joined(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)

    response = _remove_co_reviewer(client, project_id, owner_headers)

    assert response.status_code == 409


def test_cannot_remove_co_reviewer_from_solo_project(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_solo_project(client, owner_headers)

    response = _remove_co_reviewer(client, project_id, owner_headers)

    assert response.status_code == 409


def test_removed_co_reviewer_loses_project_access(client):
    d = _dual_setup(client)
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    response = client.get(
        f"/review-projects/{d['project_id']}", headers=d["co_reviewer_headers"]
    )

    assert response.status_code == 403


# --- Blocking pending Citations ---


def test_citation_awaiting_removed_co_reviewers_decision_is_blocked(client):
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    citations = client.get(
        f"/review-projects/{d['project_id']}/citations", headers=d["owner_headers"]
    ).json()

    assert citations[0]["blocked_pending_co_reviewer"] is True


def test_citation_neither_reviewer_had_decided_is_also_blocked(client):
    d = _dual_setup(client)
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    citations = client.get(
        f"/review-projects/{d['project_id']}/citations", headers=d["owner_headers"]
    ).json()

    assert citations[0]["blocked_pending_co_reviewer"] is True


def test_citation_already_decided_by_both_before_removal_is_not_blocked(client):
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "include"
    )
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    citations = client.get(
        f"/review-projects/{d['project_id']}/citations", headers=d["owner_headers"]
    ).json()

    assert citations[0]["blocked_pending_co_reviewer"] is False


def test_citation_never_had_a_co_reviewer_is_not_blocked(client):
    """Dual mode before anyone has ever joined is unblocked (#27) -- distinct
    from having had a Co-Reviewer who was later removed."""
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    _upload_one_citation(client, owner_headers, project_id)

    citations = client.get(
        f"/review-projects/{project_id}/citations", headers=owner_headers
    ).json()

    assert citations[0]["blocked_pending_co_reviewer"] is False


def test_blocked_citation_still_counts_toward_citations_needing_decision(client):
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    project = client.get(
        f"/review-projects/{d['project_id']}", headers=d["owner_headers"]
    ).json()

    assert project["citations_needing_decision"] == 1


# --- Recorded decisions and Conflicts remain on record ---


def test_removed_co_reviewers_screening_decision_remains_on_record(client):
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "include"
    )
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    detail = client.get(
        f"/review-projects/{d['project_id']}/citations/{d['citation_id']}",
        headers=d["owner_headers"],
    ).json()

    assert detail["screening_decision"]["decision"] == "include"
    assert detail["peer_screening_decision"]["decision"] == "include"


def test_pending_conflict_involving_removed_co_reviewer_stays_listable_and_resolvable(client):
    """A Conflict pending when its Co-Reviewer is removed is unaffected --
    both original decisions stay on record, and the Owner (who has final say
    regardless, per ADR 0006) can still resolve it."""
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude"
    )

    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    list_response = client.get(
        f"/review-projects/{d['project_id']}/conflicts", headers=d["owner_headers"]
    )
    assert list_response.status_code == 200
    conflicts = list_response.json()
    assert len(conflicts) == 1
    assert conflicts[0]["owner_decision"]["decision"] == "include"
    assert conflicts[0]["co_reviewer_decision"]["decision"] == "exclude"

    resolve_response = client.post(
        f"/review-projects/{d['project_id']}/conflicts/{conflicts[0]['id']}/resolve",
        json={"decision": "include", "reason": "Discussed and agreed"},
        headers=d["owner_headers"],
    )
    assert resolve_response.status_code == 200


def test_pending_conflict_survives_a_replacement_joining_before_it_is_resolved(client):
    """A Conflict remembers its own two Reviewers (#29) -- it must not become
    unreadable just because a replacement Co-Reviewer has since taken over
    co_reviewer_id, which is what it would look up if it read the pairing
    live off the Review Project instead of off itself."""
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _record_decision(
        client, d["project_id"], d["citation_id"], d["co_reviewer_headers"], "exclude"
    )
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    _add_co_reviewer(client, d["owner_headers"], d["project_id"], email="replacement@example.com")

    list_response = client.get(
        f"/review-projects/{d['project_id']}/conflicts", headers=d["owner_headers"]
    )

    assert list_response.status_code == 200
    conflicts = list_response.json()
    assert len(conflicts) == 1
    assert conflicts[0]["owner_decision"]["decision"] == "include"
    assert conflicts[0]["co_reviewer_decision"]["decision"] == "exclude"


# --- Inviting a replacement unblocks pending Citations ---


def test_owner_can_invite_a_replacement_after_removal(client):
    d = _dual_setup(client)
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    response = client.post(
        f"/review-projects/{d['project_id']}/invitations", headers=d["owner_headers"]
    )

    assert response.status_code == 201


def test_replacement_joining_unblocks_pending_citation(client):
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])

    _add_co_reviewer(client, d["owner_headers"], d["project_id"], email="replacement@example.com")

    citations = client.get(
        f"/review-projects/{d['project_id']}/citations", headers=d["owner_headers"]
    ).json()

    assert citations[0]["blocked_pending_co_reviewer"] is False


def test_replacement_co_reviewer_is_blind_like_any_first_opener(client):
    """The replacement is a fresh Reviewer -- #27's blinding applies to them
    exactly as it would to any Co-Reviewer opening a Citation for the first
    time, regardless of the predecessor's recorded decision."""
    d = _dual_setup(client)
    _record_decision(client, d["project_id"], d["citation_id"], d["owner_headers"], "include")
    _remove_co_reviewer(client, d["project_id"], d["owner_headers"])
    replacement_headers = _add_co_reviewer(
        client, d["owner_headers"], d["project_id"], email="replacement@example.com"
    )

    detail = client.get(
        f"/review-projects/{d['project_id']}/citations/{d['citation_id']}",
        headers=replacement_headers,
    ).json()

    assert detail["screening_blind"] is True
    assert detail["screening_decision"] is None
    assert detail["peer_screening_decision"] is None
