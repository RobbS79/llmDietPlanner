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


def saved_list_allowance(user) -> dict:
    """Free accounts: FREE_SAVED_LISTS_PER_MONTH per calendar month.
    An entitled subscription: unlimited (limit None)."""
    from zoneinfo import ZoneInfo

    from django.conf import settings
    from django.utils import timezone

    from diet_planner.models import SavedShoppingList

    sub = active_subscription(user)
    # Calendar months in Prague time; settings.TIME_ZONE is left as is.
    now = timezone.now().astimezone(ZoneInfo('Europe/Prague'))
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = SavedShoppingList.objects.filter(user=user, created_at__gte=month_start).count()
    if sub is not None and sub.is_entitled():
        return {'can_save': True, 'used': used, 'limit': None}
    limit = int(getattr(settings, 'FREE_SAVED_LISTS_PER_MONTH', 3))
    return {'can_save': used < limit, 'used': used, 'limit': limit}
