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


def track_paid(user, *, value, currency="CZK"):
    _enqueue(user, event_name="Purchase",
             event_id=f"paid-{user.id}-{value}",
             custom_data={"value": value, "currency": currency})
