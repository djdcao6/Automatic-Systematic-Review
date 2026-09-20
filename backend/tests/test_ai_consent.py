"""A Reviewer accepts that abstracts, PDFs and criteria go to Anthropic's API (#61).

New accounts accept it at sign-up, through either route, and the time is stored.
An account that pre-dates the notice has no time and is asked once.
"""

from datetime import UTC, datetime, timedelta

from conftest import auth_headers_for

from asr_backend import auth, crud

EMAIL = "reviewer@example.com"
PASSWORD = "correcthorse"


def _register(client, **overrides):
    payload = {"email": EMAIL, "password": PASSWORD, "ai_consent": True, **overrides}
    return client.post("/register", json=payload)


def _login(client, email=EMAIL):
    return client.post("/login", json={"email": email, "password": PASSWORD})


def _invitation_token(client) -> str:
    owner = auth_headers_for(client, "inviter@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "Dual", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner,
    ).json()["id"]
    return client.post(f"/review-projects/{project_id}/invitations", headers=owner).json()["token"]


def _accept_register(client, token, **overrides):
    payload = {"email": EMAIL, "password": PASSWORD, "ai_consent": True, **overrides}
    return client.post(f"/invitations/{token}/accept-register", json=payload)


def _me(client, access_token):
    return client.get("/me", headers={"Authorization": f"Bearer {access_token}"}).json()


def _is_recent(stamp: str) -> bool:
    return abs(datetime.now(UTC) - datetime.fromisoformat(stamp)) < timedelta(minutes=1)


def _legacy_account(db_session, client, email=EMAIL) -> dict[str, str]:
    """An account made before the notice existed: no consent time."""
    crud.create_reviewer(db_session, email, auth.hash_password(PASSWORD))
    token = _login(client, email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Sign-up ------------------------------------------------------------------------------


def test_register_without_consent_is_rejected_and_makes_no_account(client):
    response = client.post("/register", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 422
    assert _login(client).status_code == 401


def test_register_with_consent_declined_is_rejected_and_makes_no_account(client):
    response = _register(client, ai_consent=False)

    assert response.status_code == 422
    assert "AI disclosure" in response.json()["detail"][0]["msg"]
    assert _login(client).status_code == 401


def test_register_with_consent_stores_the_time(client):
    response = _register(client)

    assert response.status_code == 201
    assert _is_recent(response.json()["ai_consent_at"])
    access_token = _login(client).json()["access_token"]
    assert _is_recent(_me(client, access_token)["ai_consent_at"])


def test_accept_register_without_consent_is_rejected_and_the_invitation_stays_open(client):
    token = _invitation_token(client)

    response = client.post(
        f"/invitations/{token}/accept-register", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 422
    assert _login(client).status_code == 401
    assert client.get(f"/invitations/{token}").json()["status"] == "pending"


def test_accept_register_with_consent_declined_is_rejected_and_the_invitation_stays_open(client):
    token = _invitation_token(client)

    response = _accept_register(client, token, ai_consent=False)

    assert response.status_code == 422
    assert _login(client).status_code == 401
    assert client.get(f"/invitations/{token}").json()["status"] == "pending"


def test_accept_register_with_consent_stores_the_time(client):
    token = _invitation_token(client)

    response = _accept_register(client, token)

    assert response.status_code == 200
    assert _is_recent(_me(client, response.json()["access_token"])["ai_consent_at"])


# --- Accounts that pre-date the notice ---------------------------------------------------


def test_an_account_that_pre_dates_the_notice_has_no_consent_time(client, db_session):
    headers = _legacy_account(db_session, client)

    assert client.get("/me", headers=headers).json()["ai_consent_at"] is None


def test_accepting_the_notice_stores_the_time(client, db_session):
    headers = _legacy_account(db_session, client)

    response = client.post("/me/ai-consent", headers=headers)

    assert response.status_code == 200
    assert _is_recent(response.json()["ai_consent_at"])
    assert _is_recent(client.get("/me", headers=headers).json()["ai_consent_at"])


def test_accepting_the_notice_again_keeps_the_first_time(client, db_session):
    headers = _legacy_account(db_session, client)
    first = client.post("/me/ai-consent", headers=headers).json()["ai_consent_at"]

    second = client.post("/me/ai-consent", headers=headers).json()["ai_consent_at"]

    assert second == first


def test_accepting_the_notice_does_not_touch_another_account(client, db_session):
    headers = _legacy_account(db_session, client)
    _legacy_account(db_session, client, email="other@example.com")
    other_token = _login(client, "other@example.com").json()["access_token"]

    client.post("/me/ai-consent", headers=headers)

    assert _me(client, other_token)["ai_consent_at"] is None


def test_accepting_the_notice_needs_a_session(client):
    assert client.post("/me/ai-consent").status_code == 401
