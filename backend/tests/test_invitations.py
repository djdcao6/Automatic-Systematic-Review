"""Invite a Co-Reviewer into a Dual Review Project (#26)."""

import uuid

from conftest import auth_headers_for


def _create_dual_project(client, headers, name="Dual Review"):
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "dual"},
        headers=headers,
    ).json()["id"]


def _create_solo_project(client, headers, name="Solo Review"):
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
        headers=headers,
    ).json()["id"]


# --- Generation ---


def test_owner_can_generate_invitation(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)

    response = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert isinstance(body["token"], str) and len(body["token"]) > 20


def test_non_owner_cannot_generate_invitation(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    other_headers = auth_headers_for(client, "someone-else@example.com")
    project_id = _create_dual_project(client, owner_headers)

    response = client.post(
        f"/review-projects/{project_id}/invitations", headers=other_headers
    )

    assert response.status_code == 403


def test_solo_project_has_no_invitation_capability(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_solo_project(client, owner_headers)

    response = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    )

    assert response.status_code == 409


def test_cannot_generate_invitation_when_project_already_has_co_reviewer(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    response = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    )

    assert response.status_code == 409


def test_list_invitations_requires_owner(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    other_headers = auth_headers_for(client, "someone-else@example.com")
    project_id = _create_dual_project(client, owner_headers)
    client.post(f"/review-projects/{project_id}/invitations", headers=owner_headers)

    owner_response = client.get(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    )
    other_response = client.get(
        f"/review-projects/{project_id}/invitations", headers=other_headers
    )

    assert owner_response.status_code == 200
    assert len(owner_response.json()) == 1
    assert other_response.status_code == 403


# --- Revocation ---


def test_owner_can_revoke_outstanding_invitation(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    invitation_id = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["id"]

    response = client.post(
        f"/review-projects/{project_id}/invitations/{invitation_id}/revoke",
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"


def test_non_owner_cannot_revoke_invitation(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    other_headers = auth_headers_for(client, "someone-else@example.com")
    project_id = _create_dual_project(client, owner_headers)
    invitation_id = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["id"]

    response = client.post(
        f"/review-projects/{project_id}/invitations/{invitation_id}/revoke",
        headers=other_headers,
    )

    assert response.status_code == 403


def test_cannot_revoke_already_revoked_invitation(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    invitation_id = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["id"]
    client.post(
        f"/review-projects/{project_id}/invitations/{invitation_id}/revoke",
        headers=owner_headers,
    )

    response = client.post(
        f"/review-projects/{project_id}/invitations/{invitation_id}/revoke",
        headers=owner_headers,
    )

    assert response.status_code == 409


def test_revoked_invitation_link_cannot_be_used(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    invitation = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()
    client.post(
        f"/review-projects/{project_id}/invitations/{invitation['id']}/revoke",
        headers=owner_headers,
    )

    response = client.post(
        f"/invitations/{invitation['token']}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    assert response.status_code == 409


# --- Accepting: by registering ---


def test_get_invitation_public_details(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers, name="My Dual Review")
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]

    response = client.get(f"/invitations/{token}")

    assert response.status_code == 200
    body = response.json()
    assert body["review_project_name"] == "My Dual Review"
    assert body["status"] == "pending"


def test_get_invitation_public_details_for_unknown_token_returns_404(client):
    response = client.get("/invitations/not-a-real-token")

    assert response.status_code == 404


def test_accept_invitation_by_registering_attaches_co_reviewer(client, db_session):
    from asr_backend import crud

    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]

    response = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_project_id"] == project_id
    assert "access_token" in body

    project = crud.get_review_project(db_session, uuid.UUID(project_id))
    co_reviewer = crud.get_reviewer_by_email(db_session, "co-reviewer@example.com")
    assert project.co_reviewer_id == co_reviewer.id


def test_accepting_a_second_invitation_after_co_reviewer_joined_creates_no_orphaned_account(
    client,
):
    """A losing accept-register must not leave behind a Reviewer account no
    Invitation actually admitted (checked before crud.create_reviewer runs,
    not just by the atomic co_reviewer_id guard afterward)."""
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token_a = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    token_b = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    client.post(
        f"/invitations/{token_a}/accept-register",
        json={"email": "first-co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    response = client.post(
        f"/invitations/{token_b}/accept-register",
        json={"email": "second-co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    assert response.status_code == 409
    register_response = client.post(
        "/register",
        json={"email": "second-co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )
    assert register_response.status_code == 201


def test_accept_invitation_by_registering_rejects_taken_email(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    auth_headers_for(client, "taken@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]

    response = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "taken@example.com", "password": "correcthorse", "ai_consent": True},
    )

    assert response.status_code == 409


def test_accept_invitation_by_registering_for_unknown_token_returns_404(client):
    response = client.post(
        "/invitations/not-a-real-token/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    assert response.status_code == 404


# --- Accepting: by logging into an existing account ---


def test_accept_invitation_by_logging_in_attaches_co_reviewer(client, db_session):
    from asr_backend import crud

    owner_headers = auth_headers_for(client, "owner@example.com")
    auth_headers_for(client, "co-reviewer@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]

    response = client.post(
        f"/invitations/{token}/accept-login",
        json={"email": "co-reviewer@example.com", "password": "correcthorse"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_project_id"] == project_id

    project = crud.get_review_project(db_session, uuid.UUID(project_id))
    co_reviewer = crud.get_reviewer_by_email(db_session, "co-reviewer@example.com")
    assert project.co_reviewer_id == co_reviewer.id


def test_accept_invitation_by_logging_in_rejects_wrong_password(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    auth_headers_for(client, "co-reviewer@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]

    response = client.post(
        f"/invitations/{token}/accept-login",
        json={"email": "co-reviewer@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_owner_cannot_accept_their_own_invitation(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]

    response = client.post(
        f"/invitations/{token}/accept-login",
        json={"email": "owner@example.com", "password": "correcthorse"},
    )

    assert response.status_code == 409


# --- Reuse rejection ---


def test_accepted_invitation_cannot_be_used_again(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    response = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "someone-else@example.com", "password": "correcthorse", "ai_consent": True},
    )

    assert response.status_code == 409


def test_accepted_invitation_shows_accepted_status(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    response = client.get(f"/invitations/{token}")

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


# --- Co-Reviewer access parity (Citations, Extraction Fields, Full Text) ---
# Criteria are the exception: only the Owner may edit them (see the test below).

CSV_SAMPLE = "title,abstract,authors,year,source\nStudy,An abstract,Author,2020,PubMed\n"


def test_co_reviewer_has_owner_level_access_to_project_resources(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    co_reviewer_token = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    ).json()["access_token"]
    co_reviewer_headers = {"Authorization": f"Bearer {co_reviewer_token}"}

    assert (
        client.get(f"/review-projects/{project_id}", headers=co_reviewer_headers).status_code
        == 200
    )
    assert (
        client.post(
            f"/review-projects/{project_id}/citations",
            files={"file": ("citations.csv", CSV_SAMPLE, "text/csv")},
            headers=co_reviewer_headers,
        ).status_code
        == 201
    )
    assert (
        client.get(
            f"/review-projects/{project_id}/citations", headers=co_reviewer_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/review-projects/{project_id}/extraction-fields",
            json={"name": "Sample size", "description": None},
            headers=co_reviewer_headers,
        ).status_code
        == 201
    )


def test_co_reviewer_cannot_edit_criteria_but_can_read_them(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Adults"},
        headers=owner_headers,
    )
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    co_reviewer_token = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    ).json()["access_token"]
    co_reviewer_headers = {"Authorization": f"Bearer {co_reviewer_token}"}

    response = client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Children"},
        headers=co_reviewer_headers,
    )
    project = client.get(f"/review-projects/{project_id}", headers=co_reviewer_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the Owner can perform this action"
    assert project.json()["criteria"]["population"] == "Adults"


def test_owner_can_still_edit_criteria_after_a_co_reviewer_joins(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    )

    response = client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Adults"},
        headers=owner_headers,
    )

    assert response.status_code == 200


def test_co_reviewer_cannot_generate_or_revoke_invitations(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    invitation = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()
    co_reviewer_token = client.post(
        f"/invitations/{invitation['token']}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    ).json()["access_token"]
    co_reviewer_headers = {"Authorization": f"Bearer {co_reviewer_token}"}

    generate_response = client.post(
        f"/review-projects/{project_id}/invitations", headers=co_reviewer_headers
    )
    list_response = client.get(
        f"/review-projects/{project_id}/invitations", headers=co_reviewer_headers
    )

    assert generate_response.status_code == 403
    assert list_response.status_code == 403


def test_co_reviewer_appears_in_project_listing(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers, name="Shared Review")
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    co_reviewer_token = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
    ).json()["access_token"]
    co_reviewer_headers = {"Authorization": f"Bearer {co_reviewer_token}"}

    response = client.get("/review-projects", headers=co_reviewer_headers)

    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["Shared Review"]
