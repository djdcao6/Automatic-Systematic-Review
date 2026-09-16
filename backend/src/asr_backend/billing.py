import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import stripe
from sqlalchemy.orm import Session

from asr_backend import crud, models, schemas
from asr_backend.settings import settings

_CHECKOUT_COMPLETED = "checkout.session.completed"
_SUBSCRIPTION_UPDATED = "customer.subscription.updated"
_SUBSCRIPTION_DELETED = "customer.subscription.deleted"


def derive_plan(subscription: models.Subscription | None) -> schemas.Plan:
    """Plan is Paid for any Subscription status other than canceled, per ADR 0007.

    `active` and `past_due` both count as Paid — a failed renewal charge
    keeps access through Stripe's automatic retry window, only dropping to
    Free once Stripe gives up and cancels. No Subscription at all is Free.
    """
    if subscription is None or subscription.status == "canceled":
        return "free"
    return "paid"


class WebhookSignatureError(Exception):
    """Raised when a webhook payload's Stripe-Signature header fails verification."""


class StripeGateway:
    """Thin wrapper around the Stripe SDK, mirroring AISuggester's client boundary.

    Tests stub this at the same seam (a fake with the same method surface)
    rather than mocking the `stripe` module directly.
    """

    def __init__(self, secret_key: str, webhook_secret: str, price_id: str) -> None:
        self._webhook_secret = webhook_secret
        self._price_id = price_id
        stripe.api_key = secret_key

    def create_checkout_session(
        self,
        *,
        reviewer_id: uuid.UUID,
        reviewer_email: str,
        customer_id: str | None,
        success_url: str,
        cancel_url: str,
    ) -> Any:
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": self._price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(reviewer_id),
            # Set on the Subscription itself (not just the Checkout Session)
            # so a later customer.subscription.updated/deleted webhook can
            # identify the Reviewer without depending on checkout.session
            # .completed having already been processed first.
            "subscription_data": {"metadata": {"reviewer_id": str(reviewer_id)}},
        }
        if customer_id is not None:
            params["customer"] = customer_id
        else:
            params["customer_email"] = reviewer_email
        return stripe.checkout.Session.create(**params)

    def create_portal_session(self, *, customer_id: str, return_url: str) -> Any:
        return stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)

    def construct_event(self, payload: bytes, sig_header: str) -> Any:
        try:
            return stripe.Webhook.construct_event(payload, sig_header, self._webhook_secret)
        except (stripe.SignatureVerificationError, ValueError) as exc:
            raise WebhookSignatureError from exc


@lru_cache
def get_stripe_gateway() -> StripeGateway:
    return StripeGateway(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        price_id=settings.stripe_price_id,
    )


def _parse_period_end(epoch_seconds: int | None) -> datetime | None:
    if epoch_seconds is None:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)


def handle_webhook_event(db: Session, gateway: StripeGateway, payload: bytes, sig_header: str) -> None:
    """Verifies the webhook signature and upserts the Reviewer's Subscription.

    Handles checkout.session.completed (first subscribe) and
    customer.subscription.updated/deleted (renewal, retry, cancellation).
    Each event type carries reviewer_id independently (client_reference_id
    on the Checkout Session, metadata.reviewer_id on the Subscription
    itself), so processing doesn't depend on event delivery order.
    """
    event = gateway.construct_event(payload, sig_header)
    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == _CHECKOUT_COMPLETED:
        reviewer_id = uuid.UUID(obj["client_reference_id"])
        crud.upsert_subscription(
            db,
            reviewer_id=reviewer_id,
            stripe_customer_id=obj["customer"],
            stripe_subscription_id=obj["subscription"],
            status="active",
            current_period_end=None,
        )
    elif event_type in (_SUBSCRIPTION_UPDATED, _SUBSCRIPTION_DELETED):
        reviewer_id = uuid.UUID(obj["metadata"]["reviewer_id"])
        status = "canceled" if event_type == _SUBSCRIPTION_DELETED else obj["status"]
        crud.upsert_subscription(
            db,
            reviewer_id=reviewer_id,
            stripe_customer_id=obj["customer"],
            stripe_subscription_id=obj["id"],
            status=status,
            current_period_end=_parse_period_end(obj.get("current_period_end")),
        )
