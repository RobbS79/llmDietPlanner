"""
Billing service layer — Stripe customer/checkout helpers and webhook handlers.

Keeps Stripe calls and entitlement mutations out of the views. Webhook handlers
are idempotent (guarded by ProcessedWebhookEvent) and defensive about Stripe
API-version differences in object shape.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.models import User

from analytics.events import track_paid

from .stripe_client import stripe
from .models import Subscription, SubscriptionPlan, StripeCustomer, Tier

logger = logging.getLogger(__name__)


# --- tier <-> price resolution -------------------------------------------------

def price_id_for_tier(tier: str) -> str | None:
    """Resolve a Stripe Price id for a tier: env first, then DB override."""
    env_map = {
        Tier.STANDARD: settings.STRIPE_PRICE_STANDARD,
        Tier.PREMIUM: settings.STRIPE_PRICE_PREMIUM,
    }
    price_id = env_map.get(tier) or ''
    if price_id:
        return price_id
    plan = SubscriptionPlan.objects.filter(tier=tier).first()
    return plan.stripe_price_id or None if plan else None


def tier_for_price_id(price_id: str) -> str | None:
    """Reverse map a Stripe Price id back to our tier."""
    if not price_id:
        return None
    if price_id == settings.STRIPE_PRICE_STANDARD:
        return Tier.STANDARD
    if price_id == settings.STRIPE_PRICE_PREMIUM:
        return Tier.PREMIUM
    plan = SubscriptionPlan.objects.filter(stripe_price_id=price_id).first()
    return plan.tier if plan else None


# --- customer ------------------------------------------------------------------

def _customer_is_usable(customer_id: str) -> bool:
    """
    True if the stored Stripe customer still exists and isn't deleted.

    A stored id can go stale — the customer was deleted, or it belongs to a
    different account/mode (e.g. a test-mode customer minted before the env was
    switched to live keys). Stripe answers those with InvalidRequestError; we
    treat any such case as "mint a fresh one".
    """
    if not customer_id:
        return False
    try:
        cust = as_dict(stripe.Customer.retrieve(customer_id))
    except stripe.error.InvalidRequestError:
        return False
    return not cust.get('deleted', False)


def get_or_create_customer(user: User) -> str:
    """
    Return the user's Stripe Customer id, creating one if needed.

    Self-heals a stale stored id (deleted / wrong account or mode) by creating
    a fresh customer instead of handing checkout an id Stripe will reject.
    """
    existing = StripeCustomer.objects.filter(user=user).first()
    if existing and _customer_is_usable(existing.stripe_customer_id):
        return existing.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email or None,
        name=(user.get_full_name() or user.username) or None,
        metadata={'user_id': str(user.id), 'username': user.username},
    )
    StripeCustomer.objects.update_or_create(
        user=user, defaults={'stripe_customer_id': customer['id']},
    )
    return customer['id']


# --- shape helpers (API-version tolerant) -------------------------------------

def as_dict(obj) -> dict:
    """
    Normalize a Stripe object (or already-plain dict) to a nested plain dict.

    stripe-python's StripeObject is not a dict and lacks `.get()`, so we coerce
    via its JSON representation. Plain dicts (e.g. test fixtures) pass through.
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    try:
        return json.loads(str(obj))
    except (TypeError, ValueError):
        return {}


def _to_dt(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc)


def _period_end(sub_obj) -> datetime | None:
    """
    Extract current_period_end. In older API versions it lives on the
    subscription; in newer ones it moved to the subscription item. Try both.
    """
    ts = sub_obj.get('current_period_end')
    if not ts:
        items = (sub_obj.get('items') or {}).get('data') or []
        if items:
            ts = items[0].get('current_period_end')
    return _to_dt(ts)


def _tier_from_subscription(sub_obj) -> str | None:
    items = (sub_obj.get('items') or {}).get('data') or []
    if not items:
        return None
    price = items[0].get('price') or {}
    return tier_for_price_id(price.get('id', ''))


_STATUS_MAP = {
    'active': Subscription.Status.ACTIVE,
    'trialing': Subscription.Status.ACTIVE,
    'past_due': Subscription.Status.PAST_DUE,
    'unpaid': Subscription.Status.PAST_DUE,
    'canceled': Subscription.Status.CANCELED,
    'incomplete_expired': Subscription.Status.EXPIRED,
}


def _resolve_user(sub_obj, customer_id: str) -> User | None:
    """Find the Django user behind a Stripe subscription/customer."""
    user_id = (sub_obj.get('metadata') or {}).get('user_id')
    if user_id:
        user = User.objects.filter(id=user_id).first()
        if user:
            return user
    mapping = StripeCustomer.objects.filter(stripe_customer_id=customer_id).first()
    return mapping.user if mapping else None


def retrieve_subscription(sub_id: str) -> dict:
    """Fetch a subscription from Stripe as a plain dict (price expanded)."""
    return as_dict(stripe.Subscription.retrieve(sub_id, expand=['items.data.price']))


def upsert_subscription(user: User, sub_obj: dict, customer_id: str, *,
                        tier: str | None = None) -> Subscription | None:
    """
    Create-or-update the user's entitlement row from a Stripe subscription.

    The single source of provisioning truth, shared by every webhook handler and
    the reconcile command, so a subscription entitles regardless of *which*
    event (checkout / created / updated) reached us first or at all.

    Deliberately does NOT touch `plans_used_this_period`: a new row defaults to 0,
    and an existing row's usage must survive arbitrary `subscription.updated`
    events — only a renewal (`invoice.paid`) resets it.
    """
    tier = tier or _tier_from_subscription(sub_obj)
    if tier not in (Tier.STANDARD, Tier.PREMIUM):
        logger.error('Unknown tier for subscription %s', sub_obj.get('id'))
        return None

    StripeCustomer.objects.update_or_create(
        user=user, defaults={'stripe_customer_id': customer_id},
    )
    sub, _created = Subscription.objects.update_or_create(
        user=user,
        defaults={
            'tier': tier,
            'status': _STATUS_MAP.get(sub_obj.get('status'), Subscription.Status.ACTIVE),
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': sub_obj.get('id'),
            'current_period_end': _period_end(sub_obj),
            'cancel_at_period_end': bool(sub_obj.get('cancel_at_period_end')),
        },
    )
    return sub


# --- webhook handlers (idempotent; called after signature verification) --------

def handle_checkout_completed(event) -> None:
    session = event['data']['object']
    if session.get('mode') != 'subscription':
        return
    customer_id = session.get('customer')
    sub_id = session.get('subscription')
    if not sub_id:
        logger.warning('checkout.session.completed without subscription id')
        return

    sub_obj = as_dict(stripe.Subscription.retrieve(sub_id, expand=['items.data.price']))
    user = _resolve_user(
        {'metadata': session.get('metadata') or {}}, customer_id,
    ) or _resolve_user(sub_obj, customer_id)
    if user is None:
        logger.error('Cannot resolve user for checkout session %s', session.get('id'))
        return

    tier = (session.get('metadata') or {}).get('tier') or _tier_from_subscription(sub_obj)
    if upsert_subscription(user, sub_obj, customer_id, tier=tier) is None:
        return
    logger.info('Provisioned %s subscription for user %s', tier, user.id)
    _send_welcome_email(user, tier)

    # Fire server-side Purchase CAPI event (best-effort; never break the webhook).
    # No-ops unless the user consented. Isolated so a transient broker outage
    # can't propagate a 500 that both drops the dedup claim and re-sends email.
    try:
        plan = SubscriptionPlan.objects.filter(tier=tier).first()
        if plan is None:
            logger.warning(
                "Purchase CAPI: no SubscriptionPlan for tier=%s (user=%s); value=0",
                tier, user.id,
            )
        value = plan.price_czk if plan else 0
        track_paid(user, value=value, currency='CZK', event_id=session.get('id'))
    except Exception:  # pragma: no cover - analytics is non-critical
        logger.exception("track_paid failed (non-fatal) for user=%s", user.id)


def handle_invoice_paid(event) -> None:
    """Renewal succeeded → extend period and reset usage."""
    invoice = event['data']['object']
    sub_id = invoice.get('subscription')
    if not sub_id:
        return
    sub = Subscription.objects.filter(stripe_subscription_id=sub_id).first()
    if not sub:
        return
    sub_obj = as_dict(stripe.Subscription.retrieve(sub_id, expand=['items.data.price']))
    sub.current_period_end = _period_end(sub_obj) or sub.current_period_end
    sub.status = _STATUS_MAP.get(sub_obj.get('status'), Subscription.Status.ACTIVE)
    sub.plans_used_this_period = 0
    sub.save(update_fields=['current_period_end', 'status', 'plans_used_this_period', 'updated_at'])


def handle_payment_failed(event) -> None:
    invoice = event['data']['object']
    sub_id = invoice.get('subscription')
    sub = Subscription.objects.filter(stripe_subscription_id=sub_id).first()
    if not sub:
        return
    sub.status = Subscription.Status.PAST_DUE
    sub.save(update_fields=['status', 'updated_at'])


def handle_subscription_created(event) -> None:
    """A subscription was created (incl. directly in the Stripe dashboard, which
    never emits checkout.session.completed). Provision so it still entitles."""
    _provision_from_subscription_event(event, 'customer.subscription.created')


def handle_subscription_updated(event) -> None:
    """Sync status/period/tier — and create the row if it's missing, so an
    `updated` that races ahead of (or replaces) the checkout event still
    provisions instead of silently dropping the paying user."""
    _provision_from_subscription_event(event, 'customer.subscription.updated')


def _provision_from_subscription_event(event, label: str) -> None:
    sub_obj = event['data']['object']
    customer_id = sub_obj.get('customer')
    existing = Subscription.objects.filter(
        stripe_subscription_id=sub_obj.get('id')
    ).first()
    user = existing.user if existing else _resolve_user(sub_obj, customer_id)
    if user is None:
        logger.error('%s: cannot resolve user for subscription %s',
                     label, sub_obj.get('id'))
        return
    upsert_subscription(user, sub_obj, customer_id)


def handle_subscription_deleted(event) -> None:
    sub_obj = event['data']['object']
    sub = Subscription.objects.filter(
        stripe_subscription_id=sub_obj.get('id')
    ).first()
    if not sub:
        return
    sub.status = Subscription.Status.EXPIRED
    sub.cancel_at_period_end = False
    sub.save(update_fields=['status', 'cancel_at_period_end', 'updated_at'])


HANDLERS = {
    'checkout.session.completed': handle_checkout_completed,
    'invoice.paid': handle_invoice_paid,
    'invoice.payment_failed': handle_payment_failed,
    'customer.subscription.created': handle_subscription_created,
    'customer.subscription.updated': handle_subscription_updated,
    'customer.subscription.deleted': handle_subscription_deleted,
}


def _send_welcome_email(user: User, tier: str) -> None:
    """Best-effort welcome email on activation. Never blocks provisioning."""
    if not user.email:
        return
    try:
        from django.core.mail import send_mail
        send_mail(
            subject='Vítejte v Eatalníčku Premium' if tier == Tier.PREMIUM
            else 'Vítejte v Eatalníčku',
            message=(
                'Děkujeme za předplatné! Váš účet je aktivní a můžete začít '
                'generovat jídelníčky.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:  # pragma: no cover - email is non-critical
        logger.exception('Failed to send welcome email to user %s', user.id)
