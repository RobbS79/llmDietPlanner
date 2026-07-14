"""Consent-gated helpers that enqueue server CAPI events.

Callers pass a Django User. We read the user's MarketingAttribution row for
consent + fbp/fbc; if there is no row or consent is false, we do nothing.
Event ids are derived deterministically so a retry can't double-count.
"""
import logging

from analytics.models import MarketingAttribution
from analytics.tasks import send_capi_event_task

logger = logging.getLogger(__name__)


def _attribution(user):
    return MarketingAttribution.objects.filter(user=user).first()


def _enqueue(user, *, event_name, event_id, custom_data=None):
    attr = _attribution(user)
    if attr is None or not attr.marketing_consent:
        return
    send_capi_event_task.delay(
        event_name=event_name,
        event_id=event_id,
        email=user.email or "",
        fbp=attr.fbp,
        fbc=attr.fbc,
        event_source_url="https://eatalnicek.eu/",
        custom_data=custom_data,
    )


def track_signup(user):
    _enqueue(user, event_name="CompleteRegistration",
             event_id=f"signup-{user.id}")


def track_plan_generated(user, goal_id):
    _enqueue(user, event_name="PlanGenerated",
             event_id=f"plan-{goal_id}")


def track_paid(user, *, value, currency="CZK", event_id=None):
    # Prefer a caller-supplied dedup key (the Stripe checkout session id) —
    # it's stable across webhook retries but unique per purchase, so a
    # churn->resubscribe at the same tier/value isn't dropped by Meta's
    # event_id dedup. Fall back to the old per-user-per-value key for
    # backward compat with any other callers.
    dedup_key = f"paid-{event_id}" if event_id else f"paid-{user.id}-{value}"
    _enqueue(user, event_name="Purchase",
             event_id=dedup_key,
             custom_data={"value": value, "currency": currency})
