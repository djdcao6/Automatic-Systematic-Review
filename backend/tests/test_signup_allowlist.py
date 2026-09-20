"""Pilot sign-up allowlist and the invitation-account restriction (#60)."""

from conftest import auth_headers_for

from asr_backend import models
from asr_backend.settings import settings

PASSWORD = "correcthorse"
CSV_SAMPLE = "title,abstract,authors,year,source\nStudy,An abstract,Author,2020,PubMed\n"


def _allow(monkeypatch, value: str) -> None:
    monkeypatch.setattr(settings, "signup_allowlist", value)


def _register(client, email: str):
    return client.post("/register", json={"email": email, "password": PASSWORD})


def _login(client, email: str):
    return client.post("/login", json={"email": email, "password": PASSWORD})


def _project_payload(review_mode: str = "solo") -> dict:
    return {"name": "My Review", "merge_mode": "combine", "review_mode": review_mode}


def _dual_project_with_invitation(client, owner_headers) -> tuple[str, str]:
    project_id = client.post(
        "/review-projects", json=_project_payload("dual"), headers=owner_headers
    ).json()["id"]
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    return project_id, token


def _accept_by_registering(client, token: str, email: str):
    return client.post(
        f"/invitations/{token}/accept-register", json={"email": email, "password": PASSWORD}
    )


# --- /register ---------------------------------------------------------------


def test_an_allowlisted_email_can_register(client, monkeypatch):
    _allow(monkeypatch, "pilot@example.com")

    response = _register(client, "pilot@example.com")

    assert response.status_code == 201
    assert response.json()["email"] == "pilot@example.com"


def test_an_email_not_on_the_allowlist_gets_a_clear_403(client, monkeypatch):
    _allow(monkeypatch, "pilot@example.com")

    response = _register(client, "stranger@example.com")

    assert response.status_code == 403
    assert "invite only" in response.json()["detail"]
    assert _login(client, "stranger@example.com").status_code == 401  # no account was made


def test_an_empty_allowlist_means_nobody_can_register(client, monkeypatch):
    _allow(monkeypatch, "")

    assert _register(client, "anyone@example.com").status_code == 403


def test_the_allowlist_ignores_case_spaces_and_empty_entries(client, monkeypatch):
    _allow(monkeypatch, " First@Example.com , ,second@example.COM,")

    assert _register(client, "first@example.com").status_code == 201
    assert _register(client, "Second@Example.com").status_code == 201
    assert _register(client, "third@example.com").status_code == 403


def test_a_lone_star_opens_sign_up_to_everyone(client, monkeypatch):
    _allow(monkeypatch, "*")

    assert _register(client, "anyone@example.com").status_code == 201


def test_a_star_among_other_entries_is_not_a_wildcard_prefix_or_suffix(client, monkeypatch):
    _allow(monkeypatch, "*@example.com")

    assert _register(client, "someone@example.com").status_code == 403


def test_a_non_allowlisted_email_gets_403_even_if_it_already_has_an_account(client, monkeypatch):
    _register(client, "existing@example.com")
    _allow(monkeypatch, "pilot@example.com")

    assert _register(client, "existing@example.com").status_code == 403


def test_an_existing_account_can_still_log_in_after_leaving_the_allowlist(client, monkeypatch):
    _register(client, "existing@example.com")
    _allow(monkeypatch, "")

    assert _login(client, "existing@example.com").status_code == 200


def test_a_registered_allowlisted_account_is_not_invited_only(client, monkeypatch, db_session):
    _allow(monkeypatch, "pilot@example.com")
    _register(client, "pilot@example.com")

    reviewer = db_session.query(models.Reviewer).filter_by(email="pilot@example.com").one()

    assert reviewer.invited_only is False


# --- Accounts created through an Invitation ----------------------------------------


def test_accept_register_works_for_an_email_that_is_not_on_the_allowlist(
    client, monkeypatch, db_session
):
    owner_headers = auth_headers_for(client, "owner@example.com")
    _, token = _dual_project_with_invitation(client, owner_headers)
    _allow(monkeypatch, "owner@example.com")

    response = _accept_by_registering(client, token, "invitee@example.com")

    assert response.status_code == 200
    invitee = db_session.query(models.Reviewer).filter_by(email="invitee@example.com").one()
    assert invitee.invited_only is True


def test_an_invited_account_can_work_in_the_inviting_project(client, monkeypatch):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id, token = _dual_project_with_invitation(client, owner_headers)
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", CSV_SAMPLE, "text/csv")},
        headers=owner_headers,
    )
    citation_id = client.get(
        f"/review-projects/{project_id}/citations", headers=owner_headers
    ).json()[0]["id"]
    _allow(monkeypatch, "owner@example.com")
    invitee_token = _accept_by_registering(client, token, "invitee@example.com").json()[
        "access_token"
    ]
    invitee_headers = {"Authorization": f"Bearer {invitee_token}"}

    decision = client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "include"},
        headers=invitee_headers,
    )
    projects = client.get("/review-projects", headers=invitee_headers)

    assert decision.status_code == 200
    assert [p["id"] for p in projects.json()] == [project_id]


def test_an_invited_account_cannot_create_review_projects(client, monkeypatch):
    owner_headers = auth_headers_for(client, "owner@example.com")
    _, token = _dual_project_with_invitation(client, owner_headers)
    _allow(monkeypatch, "owner@example.com")
    invitee_token = _accept_by_registering(client, token, "invitee@example.com").json()[
        "access_token"
    ]

    response = client.post(
        "/review-projects",
        json=_project_payload(),
        headers={"Authorization": f"Bearer {invitee_token}"},
    )

    assert response.status_code == 403
    assert "invite only" in response.json()["detail"]


def test_being_added_to_the_allowlist_lifts_the_restriction(client, monkeypatch):
    owner_headers = auth_headers_for(client, "owner@example.com")
    _, token = _dual_project_with_invitation(client, owner_headers)
    _allow(monkeypatch, "owner@example.com")
    invitee_token = _accept_by_registering(client, token, "invitee@example.com").json()[
        "access_token"
    ]
    invitee_headers = {"Authorization": f"Bearer {invitee_token}"}
    assert (
        client.post("/review-projects", json=_project_payload(), headers=invitee_headers)
    ).status_code == 403

    _allow(monkeypatch, "owner@example.com, Invitee@example.com")

    response = client.post("/review-projects", json=_project_payload(), headers=invitee_headers)

    assert response.status_code == 201


def test_accept_login_for_an_allowlisted_account_is_unchanged(client, monkeypatch, db_session):
    owner_headers = auth_headers_for(client, "owner@example.com")
    _, token = _dual_project_with_invitation(client, owner_headers)
    _allow(monkeypatch, "owner@example.com, member@example.com")
    _register(client, "member@example.com")

    response = client.post(
        f"/invitations/{token}/accept-login",
        json={"email": "member@example.com", "password": PASSWORD},
    )
    member_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    assert response.status_code == 200
    member = db_session.query(models.Reviewer).filter_by(email="member@example.com").one()
    assert member.invited_only is False
    assert (
        client.post("/review-projects", json=_project_payload(), headers=member_headers)
    ).status_code == 201


def test_project_creation_is_unrestricted_for_ordinary_accounts(client):
    headers = auth_headers_for(client, "ordinary@example.com")

    response = client.post("/review-projects", json=_project_payload(), headers=headers)

    assert response.status_code == 201
