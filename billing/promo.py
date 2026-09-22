"""
Promo code domain logic — validation payloads and redemption.

100 % codes write the Subscription entitlement row directly (no Stripe).
1–99 % codes delegate to services.create_checkout_session with the coupon
attached; their redemption row is recorded by the checkout webhook.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

import stripe as stripe_lib
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from . import services
from .entitlements import active_subscription
from .models import (
    PromoCode, PromoRedemption, Subscription, SubscriptionPlan, Tier,
    PROMO_QUOTA_WINDOW,
)

REASON_MESSAGES = {
    'not_found': 'Tento kód neznáme.',
    'inactive': 'Tento kód už není aktivní.',
    'expired': 'Platnost kódu vypršela.',
    'exhausted': 'Kód už byl využit maximálním počtem uživatelů.',
    'tier_not_allowed': 'Tento kód nelze použít na zvolený tarif.',
    'already_redeemed': 'Tento kód jste už použili.',
    'already_subscribed': 'Máte aktivní předplatné, kód teď nelze uplatnit.',
    'stripe_error': 'Platbu se nepodařilo zahájit. Zkuste to prosím znovu.',
}


class RedeemError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
        self.message = REASON_MESSAGES.get(reason, reason)


logger = logging.getLogger(__name__)


def discounted_price(original: int, percent_off: int) -> int:
    """Half-up rounding (197 at 50 % -> 99), not Python's banker's round()."""
    exact = Decimal(original) * (100 - percent_off) / 100
    return int(exact.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _blocks_redemption(user: User) -> bool:
    """
    True when the user already holds a subscription a promo must not clobber:
    anything currently entitled (Stripe or promo), or a live Stripe object
    (active / past due) whose row would otherwise be overwritten.
    """
    if active_subscription(user) is not None:
        return True
    sub = Subscription.objects.filter(user=user).first()
    return bool(
        sub
        and sub.source == Subscription.Source.STRIPE
        and sub.status in (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE)
    )


def validate_payload(raw_code: str) -> dict:
    """Public, status-code-free description of a code for the pricing page."""
    code = PromoCode.normalise(raw_code)
    promo = PromoCode.objects.filter(code=code).first() if code else None
    if promo is None:
        return {'valid': False, 'reason': 'not_found'}
    reason = promo.check_redeemable()
    if reason:
        return {'valid': False, 'reason': reason}
    prices = {}
    for plan in SubscriptionPlan.objects.filter(is_active=True):
        if promo.allows_tier(plan.tier):
            prices[plan.tier] = {
                'original': plan.price_czk,
                'discounted': discounted_price(plan.price_czk, promo.percent_off),
            }
    if not prices:
        return {'valid': False, 'reason': 'tier_not_allowed'}
    return {
        'valid': True,
        'code': promo.code,
        'percent_off': promo.percent_off,
        'duration_kind': promo.duration_kind,
        'duration_months': promo.duration_months,
        'tiers': list(promo.tiers or []),
        'prices': prices,
    }


def redeem(user: User, raw_code: str, tier: str) -> dict:
    """
    Redeem `raw_code` for `user` on `tier`.

    Returns {'granted': True, 'tier'} for a 100 % grant, or
    {'granted': False, 'url'} for a Stripe Checkout redirect.
    Raises RedeemError(reason) — see REASON_MESSAGES.
    """
    code = PromoCode.normalise(raw_code)
    if tier not in Tier.values:
        raise RedeemError('tier_not_allowed')
    with transaction.atomic():
        # Row lock so two users can't both take the last slot (Postgres;
        # a no-op on SQLite, where CI runs — the boundary is still tested).
        promo = PromoCode.objects.select_for_update().filter(code=code).first() if code else None
        if promo is None:
            raise RedeemError('not_found')
        now = timezone.now()
        reason = promo.check_redeemable(now)
        if reason:
            raise RedeemError(reason)
        if not promo.allows_tier(tier):
            raise RedeemError('tier_not_allowed')
        if PromoRedemption.objects.filter(promo_code=promo, user=user).exists():
            raise RedeemError('already_redeemed')
        if _blocks_redemption(user):
            raise RedeemError('already_subscribed')

        if promo.percent_off >= 100:
            Subscription.objects.update_or_create(
                user=user,
                defaults=dict(
                    tier=tier,
                    status=Subscription.Status.ACTIVE,
                    source=Subscription.Source.PROMO,
                    stripe_customer_id='',
                    stripe_subscription_id=None,
                    current_period_end=now + PROMO_QUOTA_WINDOW,
                    grant_expires_at=promo.grant_expiry(now),
                    promo_code=promo,
                    plans_used_this_period=0,
                    cancel_at_period_end=False,
                ),
            )
            PromoRedemption.objects.create(promo_code=promo, user=user, tier=tier)
            return {'granted': True, 'tier': tier}

    # Percent path: outside the lock — Stripe round-trip must not hold the row.
    if not services.is_configured():
        raise RedeemError('stripe_error')
    try:
        url = services.create_checkout_session(user, tier, promo=promo)
    except (services.PriceNotConfigured, stripe_lib.error.StripeError):
        logger.exception('promo checkout failed: code=%s tier=%s user=%s', code, tier, user.pk)
        raise RedeemError('stripe_error')
    return {'granted': False, 'url': url}


def record_checkout_redemption(session: dict) -> None:
    """Webhook hook: write the PromoRedemption for a paid promo checkout."""
    meta = session.get('metadata') or {}
    promo_id = meta.get('promo_code_id')
    user_id = meta.get('user_id')
    if not promo_id or not user_id:
        return
    promo = PromoCode.objects.filter(id=promo_id).first()
    user = User.objects.filter(id=user_id).first()
    if promo is None or user is None:
        return
    PromoRedemption.objects.get_or_create(
        promo_code=promo, user=user,
        defaults={
            'tier': meta.get('tier') or '',
            'stripe_checkout_session_id': session.get('id') or '',
        },
    )
