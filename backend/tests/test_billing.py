"""Subscribe via Stripe Checkout & see Plan status (#39)."""

import uuid
from types import SimpleNamespace

import pytest
from conftest import auth_headers_for

from asr_backend import billing, crud, models
from asr_backend.main import app
from asr_backend.schemas import ReviewProjectCreate
from asr_backend.settings import settings

# --- Plan derivation ---


def test_plan_is_free_with_no_subscription():
    assert billing.derive_plan(None) == "free"


@pytest.mark.parametrize("status", ["active", "past_due", "trialing", "unpaid"])
def test_plan_is_paid_for_any_non_canceled_status(status):
    subscription = models.Subscription(status=status)
    assert billing.derive_plan(subscription) == "paid"


def test_plan_is_free_when_canceled():
    subscription = models.Subscription(status="canceled")
    assert billing.derive_plan(subscription) == "free"


def test_require_paid_plan_raises_with_no_subscription():
    with pytest.raises(billing.PlanNotPaidError):
        billing.require_paid_plan(None)


def test_require_paid_plan_raises_when_canceled():
    subscription = models.Subscription(status="canceled")
    with pytest.raises(billing.PlanNotPaidError):
        billing.require_paid_plan(subscription)


def test_require_paid_plan_allows_active_subscription():
    subscription = models.Subscription(status="active")
    billing.require_paid_plan(subscription)


# --- Review Project cap (#41) ---


def _own_projects(db_session, reviewer_id, count):
    for i in range(count):
        crud.create_review_project(
            db_session,
            reviewer_id,
            ReviewProjectCreate(name=f"Project {i}", merge_mode="combine", review_mode="solo"),
        )


def test_review_project_cap_is_noop_while_billing_disabled(client, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = uuid.UUID(client.get("/me", headers=headers).json()["id"])
    _own_projects(db_session, reviewer_id, 5)

    billing.check_review_project_cap(db_session, reviewer_id)


def test_review_project_cap_allows_free_reviewer_under_cap(client, billing_enabled, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = uuid.UUID(client.get("/me", headers=headers).json()["id"])

    billing.check_review_project_cap(db_session, reviewer_id)


def test_review_project_cap_blocks_free_reviewer_at_cap(client, billing_enabled, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = uuid.UUID(client.get("/me", headers=headers).json()["id"])
    _own_projects(db_session, reviewer_id, 1)

    with pytest.raises(billing.ReviewProjectCapError):
        billing.check_review_project_cap(db_session, reviewer_id)


def test_review_project_cap_blocks_free_reviewer_already_over_cap(
    client, billing_enabled, db_session
):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = uuid.UUID(client.get("/me", headers=headers).json()["id"])
    _own_projects(db_session, reviewer_id, 3)

    with pytest.raises(billing.ReviewProjectCapError):
        billing.check_review_project_cap(db_session, reviewer_id)


def test_review_project_cap_never_blocks_paid_reviewer(client, billing_enabled, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = uuid.UUID(client.get("/me", headers=headers).json()["id"])
    _own_projects(db_session, reviewer_id, 3)
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
        )
    )
    db_session.commit()

    billing.check_review_project_cap(db_session, reviewer_id)


# --- Flag-off hidden state ---


def test_get_subscription_404s_while_billing_disabled(client):
    headers = auth_headers_for(client, "owner@example.com")

    response = client.get("/me/subscription", headers=headers)

    assert response.status_code == 404


def test_checkout_session_404s_while_billing_disabled(client):
    headers = auth_headers_for(client, "owner@example.com")

    response = client.post("/billing/checkout-session", headers=headers)

    assert response.status_code == 404


@pytest.fixture
def billing_enabled(monkeypatch):
    monkeypatch.setattr(settings, "billing_enabled", True)


# --- GET /me/subscription ---


def test_get_subscription_reports_free_with_no_subscription(client, billing_enabled):
    headers = auth_headers_for(client, "owner@example.com")

    response = client.get("/me/subscription", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"plan": "free", "status": None}


def test_get_subscription_reports_paid_for_active_status(client, billing_enabled, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
        )
    )
    db_session.commit()

    response = client.get("/me/subscription", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"plan": "paid", "status": "active"}


def test_get_subscription_reports_free_for_canceled_status(client, billing_enabled, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="canceled",
        )
    )
    db_session.commit()

    response = client.get("/me/subscription", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"plan": "free", "status": "canceled"}


# --- POST /billing/checkout-session ---


class _FakeGateway:
    def __init__(
        self,
        checkout_url="https://stripe.test/checkout/session_123",
        portal_url="https://stripe.test/portal/session_123",
        event=None,
    ):
        self.checkout_url = checkout_url
        self.portal_url = portal_url
        self.event = event
        self.checkout_calls: list[dict] = []
        self.portal_calls: list[dict] = []

    def create_checkout_session(self, **kwargs):
        self.checkout_calls.append(kwargs)
        return SimpleNamespace(url=self.checkout_url)

    def create_portal_session(self, *, customer_id, return_url):
        self.portal_calls.append({"customer_id": customer_id})
        return SimpleNamespace(url=self.portal_url)

    def construct_event(self, payload, sig_header):
        if self.event is None:
            raise billing.WebhookSignatureError()
        return self.event


@pytest.fixture
def fake_gateway():
    fake = _FakeGateway()
    app.dependency_overrides[billing.get_stripe_gateway] = lambda: fake
    yield fake
    app.dependency_overrides.pop(billing.get_stripe_gateway, None)


def test_checkout_session_returns_stripe_url(client, billing_enabled, fake_gateway):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]

    response = client.post("/billing/checkout-session", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"url": fake_gateway.checkout_url}
    assert len(fake_gateway.checkout_calls) == 1
    call = fake_gateway.checkout_calls[0]
    assert str(call["reviewer_id"]) == reviewer_id
    assert call["reviewer_email"] == "owner@example.com"
    assert call["customer_id"] is None


def test_checkout_session_reuses_existing_stripe_customer(
    client, billing_enabled, fake_gateway, db_session
):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_existing",
            stripe_subscription_id="sub_existing",
            status="canceled",
        )
    )
    db_session.commit()

    client.post("/billing/checkout-session", headers=headers)

    assert fake_gateway.checkout_calls[0]["customer_id"] == "cus_existing"


# --- POST /billing/webhook ---


def test_webhook_rejects_invalid_signature(client, billing_enabled, fake_gateway):
    response = client.post(
        "/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "bad"},
    )

    assert response.status_code == 400


def test_webhook_checkout_completed_creates_subscription(
    client, billing_enabled, fake_gateway, db_session
):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    fake_gateway.event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": reviewer_id,
                "customer": "cus_new",
                "subscription": "sub_new",
            }
        },
    }

    response = client.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "valid"}
    )

    assert response.status_code == 204
    subscription = (
        db_session.query(models.Subscription)
        .filter(models.Subscription.reviewer_id == reviewer_id)
        .one()
    )
    assert subscription.status == "active"
    assert subscription.stripe_customer_id == "cus_new"
    assert subscription.stripe_subscription_id == "sub_new"


def test_webhook_subscription_updated_syncs_status(
    client, billing_enabled, fake_gateway, db_session
):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
        )
    )
    db_session.commit()
    fake_gateway.event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "past_due",
                "current_period_end": 1999999999,
                "metadata": {"reviewer_id": reviewer_id},
            }
        },
    }

    response = client.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "valid"}
    )

    assert response.status_code == 204
    subscription = (
        db_session.query(models.Subscription)
        .filter(models.Subscription.reviewer_id == reviewer_id)
        .one()
    )
    assert subscription.status == "past_due"
    assert subscription.current_period_end is not None


# --- POST /billing/portal-session ---


def test_portal_session_404s_while_billing_disabled(client):
    headers = auth_headers_for(client, "owner@example.com")

    response = client.post("/billing/portal-session", headers=headers)

    assert response.status_code == 404


def test_portal_session_rejects_free_reviewer(client, billing_enabled, fake_gateway):
    headers = auth_headers_for(client, "owner@example.com")

    response = client.post("/billing/portal-session", headers=headers)

    assert response.status_code == 403
    assert fake_gateway.portal_calls == []


def test_portal_session_rejects_canceled_subscription(
    client, billing_enabled, fake_gateway, db_session
):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="canceled",
        )
    )
    db_session.commit()

    response = client.post("/billing/portal-session", headers=headers)

    assert response.status_code == 403
    assert fake_gateway.portal_calls == []


def test_portal_session_returns_stripe_url_for_paid_reviewer(
    client, billing_enabled, fake_gateway, db_session
):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
        )
    )
    db_session.commit()

    response = client.post("/billing/portal-session", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"url": fake_gateway.portal_url}
    assert fake_gateway.portal_calls == [{"customer_id": "cus_1"}]


def test_cancel_scheduled_but_not_effective_keeps_plan_paid(
    client, billing_enabled, fake_gateway, db_session
):
    """A Portal cancel sets cancel_at_period_end but Stripe's status stays
    'active' until the period actually ends — only then does it send
    customer.subscription.deleted. Until that happens, Plan must stay Paid.
    """
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
        )
    )
    db_session.commit()
    fake_gateway.event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "active",
                "cancel_at_period_end": True,
                "current_period_end": 1999999999,
                "metadata": {"reviewer_id": reviewer_id},
            }
        },
    }

    response = client.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "valid"}
    )

    assert response.status_code == 204
    subscription = (
        db_session.query(models.Subscription)
        .filter(models.Subscription.reviewer_id == reviewer_id)
        .one()
    )
    assert subscription.status == "active"
    assert billing.derive_plan(subscription) == "paid"


def test_webhook_subscription_deleted_marks_canceled(
    client, billing_enabled, fake_gateway, db_session
):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
        )
    )
    db_session.commit()
    fake_gateway.event = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "canceled",
                "metadata": {"reviewer_id": reviewer_id},
            }
        },
    }

    response = client.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "valid"}
    )

    assert response.status_code == 204
    subscription = (
        db_session.query(models.Subscription)
        .filter(models.Subscription.reviewer_id == reviewer_id)
        .one()
    )
    assert subscription.status == "canceled"
