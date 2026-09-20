import jwt

from asr_backend.settings import settings


def _register(client, email="reviewer@example.com", password="correcthorse"):
    return client.post("/register", json={"email": email, "password": password, "ai_consent": True})


def test_register_creates_reviewer(client):
    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "reviewer@example.com"
    assert "id" in body
    assert "created_at" in body
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_rejects_duplicate_email(client):
    _register(client)

    response = _register(client)

    assert response.status_code == 409


def test_register_rejects_duplicate_email_case_insensitively(client):
    _register(client, email="Reviewer@Example.com")

    response = _register(client, email="reviewer@example.com")

    assert response.status_code == 409


def test_login_is_case_insensitive_on_email(client):
    _register(client, email="Reviewer@Example.com")

    response = client.post(
        "/login", json={"email": "reviewer@example.com", "password": "correcthorse"}
    )

    assert response.status_code == 200


def test_register_rejects_short_password(client):
    response = client.post(
        "/register", json={"email": "reviewer@example.com", "password": "short", "ai_consent": True}
    )

    assert response.status_code == 422


def test_register_rejects_invalid_email(client):
    response = client.post(
        "/register", json={"email": "not-an-email", "password": "correcthorse", "ai_consent": True}
    )

    assert response.status_code == 422


def test_login_returns_jwt(client):
    _register(client)

    response = client.post(
        "/login", json={"email": "reviewer@example.com", "password": "correcthorse"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(
        body["access_token"], settings.jwt_secret_key, algorithms=["HS256"]
    )
    assert "sub" in payload
    assert "exp" in payload


def test_login_rejects_wrong_password(client):
    _register(client)

    response = client.post(
        "/login", json={"email": "reviewer@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post(
        "/login", json={"email": "nobody@example.com", "password": "correcthorse"}
    )

    assert response.status_code == 401


def test_login_wrong_password_and_unknown_email_give_same_error(client):
    _register(client)

    wrong_password = client.post(
        "/login", json={"email": "reviewer@example.com", "password": "wrong-password"}
    )
    unknown_email = client.post(
        "/login", json={"email": "nobody@example.com", "password": "correcthorse"}
    )

    assert wrong_password.status_code == unknown_email.status_code
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_me_resolves_current_reviewer_from_token(client):
    _register(client)
    token = client.post(
        "/login", json={"email": "reviewer@example.com", "password": "correcthorse"}
    ).json()["access_token"]

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "reviewer@example.com"


def test_me_rejects_missing_token(client):
    response = client.get("/me")

    assert response.status_code == 401


def test_me_rejects_invalid_token(client):
    response = client.get("/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_me_rejects_expired_token(client):
    _register(client)
    reviewer_id = _register(client, email="other@example.com").json()["id"]
    expired_token = jwt.encode(
        {"sub": reviewer_id, "exp": 1},
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    response = client.get("/me", headers={"Authorization": f"Bearer {expired_token}"})

    assert response.status_code == 401
