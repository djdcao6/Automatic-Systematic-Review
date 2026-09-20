"""Rate limits on login and sign-up (#59)."""

from conftest import auth_headers_for
from starlette.requests import Request

from asr_backend import rate_limit
from asr_backend.rate_limit import SlidingWindowLimiter
from asr_backend.settings import settings

PASSWORD = "correcthorse"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _request(forwarded_for: str | None = None, client_host: str = "10.0.0.1") -> Request:
    headers = [(b"x-forwarded-for", forwarded_for.encode())] if forwarded_for else []
    return Request({"type": "http", "headers": headers, "client": (client_host, 5000)})


# --- The limiter itself -------------------------------------------------------


def test_limiter_allows_up_to_the_limit():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60, clock=FakeClock())

    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]


def test_limiter_blocks_a_burst_and_says_how_long_to_wait():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.hit("a")
    clock.advance(10)

    assert limiter.hit("a") == 50


def test_limiter_keeps_keys_apart():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=FakeClock())
    limiter.hit("a")

    assert limiter.hit("a") is not None
    assert limiter.hit("b") is None


def test_limiter_lets_a_key_back_in_once_the_window_has_passed():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.hit("a")
    limiter.hit("a")
    assert limiter.hit("a") is not None

    clock.advance(60)

    assert limiter.hit("a") is None


def test_limiter_frees_one_slot_at_a_time_as_old_hits_expire():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.hit("a")
    clock.advance(30)
    limiter.hit("a")
    clock.advance(31)  # the first hit is now 61s old, the second 31s

    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None


def test_a_blocked_hit_does_not_extend_the_block():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("a")
    for _ in range(5):
        clock.advance(10)
        assert limiter.hit("a") is not None

    clock.advance(10)  # 60s after the one recorded hit

    assert limiter.hit("a") is None


def test_wait_is_never_reported_as_zero():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("a")
    clock.advance(59.9)

    assert limiter.hit("a") == 1


def test_limiter_forgets_keys_that_have_expired():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60, clock=clock)
    for n in range(50):
        limiter.hit(f"email-{n}")
    clock.advance(61)

    for _ in range(rate_limit._SWEEP_EVERY):
        limiter.hit("live")

    assert list(limiter._hits) == ["live"]


# --- Finding the caller's address -----------------------------------------------


def test_client_ip_is_the_connection_address_by_default():
    assert rate_limit.client_ip(_request("1.1.1.1", client_host="10.0.0.1")) == "10.0.0.1"


def test_client_ip_ignores_a_spoofable_header_unless_proxies_are_configured(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 0)

    assert rate_limit.client_ip(_request("6.6.6.6, 7.7.7.7")) == "10.0.0.1"


def test_client_ip_counts_hops_from_the_right(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    assert rate_limit.client_ip(_request("6.6.6.6, 9.9.9.9")) == "9.9.9.9"

    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    assert rate_limit.client_ip(_request("6.6.6.6, 9.9.9.9, 8.8.8.8")) == "9.9.9.9"


def test_client_ip_falls_back_when_the_header_is_shorter_than_the_proxy_count(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)

    assert rate_limit.client_ip(_request("9.9.9.9")) == "10.0.0.1"
    assert rate_limit.client_ip(_request(None)) == "10.0.0.1"


# --- On the routes --------------------------------------------------------------


def _tighten(monkeypatch, attempts, *, per_ip=None, per_email=None):
    if per_ip is not None:
        monkeypatch.setattr(attempts.per_ip, "limit", per_ip)
    if per_email is not None:
        monkeypatch.setattr(attempts.per_email, "limit", per_email)
    rate_limit.reset_all()


def _login(client, email, password=PASSWORD, **kwargs):
    return client.post("/login", json={"email": email, "password": password}, **kwargs)


def _register(client, email, password=PASSWORD):
    return client.post("/register", json={"email": email, "password": password})


def _invitation_token(client) -> str:
    owner = auth_headers_for(client, "inviter@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "Dual", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner,
    ).json()["id"]
    return client.post(f"/review-projects/{project_id}/invitations", headers=owner).json()["token"]


def test_normal_use_is_not_limited(client):
    _register(client, "me@example.com")

    responses = [_login(client, "me@example.com") for _ in range(5)]

    assert [r.status_code for r in responses] == [200] * 5


def test_login_is_blocked_after_too_many_attempts_on_one_email(client, monkeypatch):
    _register(client, "victim@example.com")
    _tighten(monkeypatch, rate_limit.login_attempts, per_email=3)

    wrong = [_login(client, "victim@example.com", "wrong-password") for _ in range(3)]
    blocked = _login(client, "victim@example.com", "wrong-password")

    assert [r.status_code for r in wrong] == [401, 401, 401]
    assert blocked.status_code == 429
    assert "Too many attempts" in blocked.json()["detail"]
    assert int(blocked.headers["Retry-After"]) >= 1


def test_the_right_password_is_also_blocked_while_the_limit_holds(client, monkeypatch):
    _register(client, "victim@example.com")
    _tighten(monkeypatch, rate_limit.login_attempts, per_email=2)
    for _ in range(2):
        _login(client, "victim@example.com", "wrong-password")

    assert _login(client, "victim@example.com").status_code == 429


def test_one_emails_limit_does_not_block_other_emails(client, monkeypatch):
    _register(client, "victim@example.com")
    _register(client, "other@example.com")
    _tighten(monkeypatch, rate_limit.login_attempts, per_email=2)
    for _ in range(3):
        _login(client, "victim@example.com", "wrong-password")

    assert _login(client, "other@example.com").status_code == 200


def test_login_is_blocked_after_too_many_attempts_from_one_address(client, monkeypatch):
    _tighten(monkeypatch, rate_limit.login_attempts, per_ip=3)

    statuses = [_login(client, f"guess-{n}@example.com").status_code for n in range(4)]

    assert statuses == [401, 401, 401, 429]


def test_a_blocked_client_can_try_again_once_the_window_has_passed(client, monkeypatch):
    _register(client, "victim@example.com")
    clock = FakeClock()
    monkeypatch.setattr(rate_limit.login_attempts.per_email, "clock", clock)
    _tighten(monkeypatch, rate_limit.login_attempts, per_email=2)
    for _ in range(2):
        _login(client, "victim@example.com", "wrong-password")
    assert _login(client, "victim@example.com").status_code == 429

    clock.advance(rate_limit.login_attempts.per_email.window_seconds)

    assert _login(client, "victim@example.com").status_code == 200


def test_invitation_accept_login_shares_the_login_budget(client, monkeypatch):
    token = _invitation_token(client)
    _register(client, "victim@example.com")
    _tighten(monkeypatch, rate_limit.login_attempts, per_email=2)
    for _ in range(2):
        _login(client, "victim@example.com", "wrong-password")

    response = client.post(
        f"/invitations/{token}/accept-login",
        json={"email": "victim@example.com", "password": PASSWORD},
    )

    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_invitation_accept_login_is_limited_on_its_own_too(client, monkeypatch):
    token = _invitation_token(client)
    _tighten(monkeypatch, rate_limit.login_attempts, per_email=2)

    statuses = [
        client.post(
            f"/invitations/{token}/accept-login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        ).status_code
        for _ in range(3)
    ]

    assert statuses == [401, 401, 429]


def test_register_is_blocked_after_too_many_attempts_from_one_address(client, monkeypatch):
    _tighten(monkeypatch, rate_limit.register_attempts, per_ip=2)

    statuses = [_register(client, f"new-{n}@example.com").status_code for n in range(3)]

    assert statuses == [201, 201, 429]


def test_register_is_blocked_after_too_many_attempts_on_one_email(client, monkeypatch):
    _tighten(monkeypatch, rate_limit.register_attempts, per_email=2)

    statuses = [_register(client, "same@example.com").status_code for _ in range(3)]

    assert statuses == [201, 409, 429]


def test_invitation_accept_register_shares_the_register_budget(client, monkeypatch):
    token = _invitation_token(client)
    _tighten(monkeypatch, rate_limit.register_attempts, per_ip=1)
    _register(client, "first@example.com")

    response = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": "second@example.com", "password": PASSWORD},
    )

    assert response.status_code == 429


def test_login_and_register_have_separate_budgets(client, monkeypatch):
    _tighten(monkeypatch, rate_limit.login_attempts, per_ip=1)
    _login(client, "a@example.com")
    assert _login(client, "b@example.com").status_code == 429

    assert _register(client, "c@example.com").status_code == 201


def test_a_limited_client_can_still_use_the_rest_of_the_api(client, monkeypatch):
    _tighten(monkeypatch, rate_limit.login_attempts, per_ip=1)
    _login(client, "a@example.com")
    assert _login(client, "b@example.com").status_code == 429

    assert client.get("/health").status_code == 200


def test_clients_behind_a_proxy_are_limited_separately(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    _tighten(monkeypatch, rate_limit.login_attempts, per_ip=1)

    first = _login(client, "a@example.com", headers={"X-Forwarded-For": "1.1.1.1"})
    repeat = _login(client, "b@example.com", headers={"X-Forwarded-For": "1.1.1.1"})
    other = _login(client, "c@example.com", headers={"X-Forwarded-For": "2.2.2.2"})

    assert (first.status_code, repeat.status_code, other.status_code) == (401, 429, 401)


def test_a_spoofed_forwarded_header_does_not_dodge_the_limit_when_no_proxy_is_configured(
    client, monkeypatch
):
    _tighten(monkeypatch, rate_limit.login_attempts, per_ip=1)

    _login(client, "a@example.com", headers={"X-Forwarded-For": "1.1.1.1"})
    second = _login(client, "b@example.com", headers={"X-Forwarded-For": "2.2.2.2"})

    assert second.status_code == 429
