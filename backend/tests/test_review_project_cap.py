"""Free-tier Review-Project cap (#41)."""

import pytest
from conftest import auth_headers_for

from asr_backend import models
from asr_backend.settings import settings


@pytest.fixture
def billing_enabled(monkeypatch):
    monkeypatch.setattr(settings, "billing_enabled", True)


def _create_project(client, headers, name="Review"):
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
        headers=headers,
    )


# --- Flag off: never blocked ---


def test_flag_off_never_blocks_creating_many_projects(client):
    headers = auth_headers_for(client, "owner@example.com")
    _create_project(client, headers, "First")

    response = _create_project(client, headers, "Second")

    assert response.status_code == 201


# --- Flag on, Free Reviewer ---


def test_free_reviewer_can_create_first_project(client, billing_enabled):
    headers = auth_headers_for(client, "owner@example.com")

    response = _create_project(client, headers, "First")

    assert response.status_code == 201


def test_free_reviewer_blocked_from_second_project(client, billing_enabled):
    headers = auth_headers_for(client, "owner@example.com")
    _create_project(client, headers, "First")

    response = _create_project(client, headers, "Second")

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "Free Plan" in detail
    assert "Account/Billing" in detail


def test_free_reviewer_blocked_project_is_not_created(client, billing_enabled):
    headers = auth_headers_for(client, "owner@example.com")
    _create_project(client, headers, "First")

    _create_project(client, headers, "Second")

    names = [p["name"] for p in client.get("/review-projects", headers=headers).json()]
    assert names == ["First"]


# --- Flag on, Paid Reviewer ---


def test_paid_reviewer_never_blocked(client, billing_enabled, db_session):
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
    _create_project(client, headers, "First")
    _create_project(client, headers, "Second")

    response = _create_project(client, headers, "Third")

    assert response.status_code == 201


# --- Already over the cap (grandfathered / downgraded) ---


def test_reviewer_over_cap_keeps_access_to_existing_projects(client, billing_enabled, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]
    # Grandfathered in while Paid, then downgraded to Free (canceled),
    # already owning more than the cap.
    db_session.add(
        models.Subscription(
            reviewer_id=reviewer_id,
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            status="active",
        )
    )
    db_session.commit()
    first_id = _create_project(client, headers, "First").json()["id"]
    second_id = _create_project(client, headers, "Second").json()["id"]
    subscription = (
        db_session.query(models.Subscription)
        .filter(models.Subscription.reviewer_id == reviewer_id)
        .one()
    )
    subscription.status = "canceled"
    db_session.commit()

    assert client.get(f"/review-projects/{first_id}", headers=headers).status_code == 200
    assert client.get(f"/review-projects/{second_id}", headers=headers).status_code == 200
    assert len(client.get("/review-projects", headers=headers).json()) == 2


def test_reviewer_over_cap_blocked_from_creating_another(client, billing_enabled, db_session):
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
    _create_project(client, headers, "First")
    _create_project(client, headers, "Second")
    subscription = (
        db_session.query(models.Subscription)
        .filter(models.Subscription.reviewer_id == reviewer_id)
        .one()
    )
    subscription.status = "canceled"
    db_session.commit()

    response = _create_project(client, headers, "Third")

    assert response.status_code == 403


# --- Co-Reviewer participation never counts ---


def test_co_reviewer_participation_does_not_count_toward_participants_cap(
    client, billing_enabled
):
    owner_headers = auth_headers_for(client, "owner@example.com")
    co_reviewer_headers = auth_headers_for(client, "co-reviewer@example.com")
    dual_project_id = client.post(
        "/review-projects",
        json={"name": "Dual Review", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner_headers,
    ).json()["id"]
    token = client.post(
        f"/review-projects/{dual_project_id}/invitations", headers=owner_headers
    ).json()["token"]
    client.post(
        f"/invitations/{token}/accept-login",
        json={"email": "co-reviewer@example.com", "password": "correcthorse"},
    )

    # The Co-Reviewer participates in the Owner's project but owns none of
    # their own yet — that participation must not count toward their cap.
    response = _create_project(client, co_reviewer_headers, "Co-Reviewer's Own Project")

    assert response.status_code == 201


def test_accepting_invitation_never_checks_the_co_reviewers_own_cap(client, billing_enabled):
    """Accepting an invitation attaches an existing Review Project rather
    than creating one, so the cap check never applies to it — a Co-Reviewer
    already at their own cap can still join someone else's project."""
    owner_headers = auth_headers_for(client, "owner@example.com")
    co_reviewer_headers = auth_headers_for(client, "co-reviewer@example.com")
    # The Co-Reviewer already owns their own single Free-Plan project (at cap).
    _create_project(client, co_reviewer_headers, "Co-Reviewer's Own Project")
    dual_project_id = client.post(
        "/review-projects",
        json={"name": "Dual Review", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner_headers,
    ).json()["id"]
    token = client.post(
        f"/review-projects/{dual_project_id}/invitations", headers=owner_headers
    ).json()["token"]

    response = client.post(
        f"/invitations/{token}/accept-login",
        json={"email": "co-reviewer@example.com", "password": "correcthorse"},
    )

    assert response.status_code == 200
