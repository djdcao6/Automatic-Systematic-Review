"""bcrypt reads at most 72 bytes of a password (#59).

Passwords are counted in bytes, not characters: accented letters and emoji take
2 to 4 bytes each. Registration rejects a longer one up front; login treats one
as a wrong password instead of failing inside bcrypt.
"""

from conftest import auth_headers_for

from asr_backend import auth

EMAIL = "reviewer@example.com"
GOOD = "correcthorse"
ASCII_73 = "a" * 73
# 40 characters, 80 bytes: under a 72-character limit but over the 72-byte one.
ACCENTED_80_BYTES = "é" * 40


def _register(client, password, email=EMAIL):
    return client.post("/register", json={"email": email, "password": password})


def _login(client, password, email=EMAIL):
    return client.post("/login", json={"email": email, "password": password})


def _invitation_token(client) -> str:
    owner = auth_headers_for(client, "inviter@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "Dual", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner,
    ).json()["id"]
    return client.post(f"/review-projects/{project_id}/invitations", headers=owner).json()["token"]


def test_login_with_a_password_over_72_bytes_is_a_401_not_a_500(client):
    _register(client, GOOD)

    response = _login(client, ASCII_73)

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_with_a_multibyte_password_over_72_bytes_is_a_401(client):
    _register(client, GOOD)

    assert _login(client, ACCENTED_80_BYTES).status_code == 401


def test_login_with_a_long_password_for_an_unknown_email_is_the_same_401(client):
    response = _login(client, ASCII_73, email="nobody@example.com")

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_register_rejects_a_password_over_72_bytes(client):
    response = _register(client, ASCII_73)

    assert response.status_code == 422
    assert "72 bytes" in response.json()["detail"][0]["msg"]


def test_register_counts_bytes_not_characters(client):
    response = _register(client, ACCENTED_80_BYTES)

    assert response.status_code == 422
    assert "72 bytes" in response.json()["detail"][0]["msg"]


def test_a_rejected_password_does_not_create_an_account(client):
    _register(client, ASCII_73)

    assert _login(client, GOOD).status_code == 401
    assert _register(client, GOOD).status_code == 201


def test_a_password_of_exactly_72_bytes_works(client):
    password = "a" * 72

    assert _register(client, password).status_code == 201
    assert _login(client, password).status_code == 200


def test_a_multibyte_password_of_exactly_72_bytes_works(client):
    password = "é" * 36  # 72 bytes

    assert _register(client, password).status_code == 201
    assert _login(client, password).status_code == 200


def test_the_minimum_length_is_still_8_characters(client):
    assert _register(client, "short").status_code == 422
    assert _register(client, "é" * 8).status_code == 201


def test_accept_register_rejects_a_password_over_72_bytes(client):
    token = _invitation_token(client)

    response = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": EMAIL, "password": ACCENTED_80_BYTES},
    )

    assert response.status_code == 422
    assert _login(client, GOOD).status_code == 401  # no account was made


def test_accept_login_with_a_password_over_72_bytes_is_a_401(client):
    token = _invitation_token(client)
    _register(client, GOOD)

    response = client.post(
        f"/invitations/{token}/accept-login",
        json={"email": EMAIL, "password": ASCII_73},
    )

    assert response.status_code == 401


def test_verify_password_reports_an_over_length_password_as_wrong():
    hashed = auth.hash_password(GOOD)

    assert auth.verify_password(ASCII_73, hashed) is False
    assert auth.verify_password(GOOD, hashed) is True
