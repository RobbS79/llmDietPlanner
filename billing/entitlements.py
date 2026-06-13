"""
Entitlement logic — the single place that answers "can this user generate?".

Paid path: an active Stripe-backed Subscription still within its monthly quota.
Free path: the existing UserProfile.free_generations_remaining counter (unchanged).

See docs/stripe-billing-plan.md §2.1 / §5.
"""
from __future__ import annotations

from django.contrib.auth.models import User

from .models import Subscription


def active_subscription(user: User) -> Subscription | None:
    """Return the user's entitled (active, unexpired) subscription, else None."""
    sub = Subscription.objects.filter(user=user).first()
    if sub and sub.is_entitled():
        return sub
    return None


def allow_generation(user: User) -> bool:
    """
    True if the user may generate a meal plan right now.

    Paid subscribers consume monthly quota; everyone else falls back to the
    free-generation counter. Pure read — callers decrement on success.
    """
    sub = active_subscription(user)
    if sub and sub.within_monthly_quota():
        return True
    return user.profile.has_free_generations()
