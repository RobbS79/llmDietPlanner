"""
Promo code tests: model rules, validate/redeem endpoints, Stripe coupon sync,
webhook redemption recording, and precedence against Stripe subscriptions.
Stripe network calls are mocked throughout.
"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import services
from .models import (
    PromoCode, PromoRedemption, Subscription, SubscriptionPlan, Tier,
)


def _plans():
    SubscriptionPlan.objects.get_or_create(
        tier=Tier.STANDARD, defaults=dict(
            name='Vařto Standard', price_czk=99, monthly_plan_quota=7,
            edits_per_plan=10, allow_multi_store=False, sort_order=1),
    )
    SubscriptionPlan.objects.get_or_create(
        tier=Tier.PREMIUM, defaults=dict(
            name='Vařto Premium', price_czk=199, monthly_plan_quota=30,
            edits_per_plan=5, allow_multi_store=True, sort_order=2),
    )


def _code(**kw):
    defaults = dict(code='LETO2026', percent_off=100,
                    duration_kind=PromoCode.Duration.LIFETIME)
    defaults.update(kw)
    return PromoCode.objects.create(**defaults)


class PromoCodeModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')

    def test_code_is_stored_uppercase(self):
        p = _code(code='  leto2026 ')
        self.assertEqual(p.code, 'LETO2026')

    def test_redeemable_when_fresh(self):
        self.assertIsNone(_code().check_redeemable())

    def test_inactive(self):
        self.assertEqual(_code(is_active=False).check_redeemable(), 'inactive')

    def test_expired(self):
        p = _code(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(p.check_redeemable(), 'expired')

    def test_exhausted_at_exactly_max(self):
        p = _code(max_redemptions=1)
        PromoRedemption.objects.create(promo_code=p, user=self.user, tier=Tier.PREMIUM)
        self.assertEqual(p.check_redeemable(), 'exhausted')

    def test_unlimited_when_max_is_null(self):
        p = _code(max_redemptions=None)
        PromoRedemption.objects.create(promo_code=p, user=self.user, tier=Tier.PREMIUM)
        self.assertIsNone(p.check_redeemable())

    def test_allows_tier(self):
        self.assertTrue(_code(tiers=[]).allows_tier('standard'))
        self.assertTrue(_code(code='B', tiers=['premium']).allows_tier('premium'))
        self.assertFalse(_code(code='C', tiers=['premium']).allows_tier('standard'))

    def test_grant_expiry_lifetime(self):
        self.assertIsNone(_code().grant_expiry(timezone.now()))

    def test_grant_expiry_months(self):
        now = timezone.now().replace(year=2026, month=1, day=31, hour=12)
        p = _code(duration_kind=PromoCode.Duration.MONTHS, duration_months=1)
        exp = p.grant_expiry(now)
        self.assertEqual((exp.year, exp.month, exp.day), (2026, 2, 28))

    def test_grant_expiry_first_invoice_is_one_month(self):
        now = timezone.now().replace(year=2026, month=3, day=10, hour=12)
        p = _code(duration_kind=PromoCode.Duration.FIRST_INVOICE)
        exp = p.grant_expiry(now)
        self.assertEqual((exp.year, exp.month, exp.day), (2026, 4, 10))

    def test_one_redemption_per_user_per_code(self):
        p = _code()
        PromoRedemption.objects.create(promo_code=p, user=self.user, tier=Tier.PREMIUM)
        with self.assertRaises(IntegrityError):
            PromoRedemption.objects.create(promo_code=p, user=self.user, tier=Tier.PREMIUM)

    def test_clean_requires_duration_months_for_months_kind(self):
        p = PromoCode(code='D1', percent_off=50, duration_kind=PromoCode.Duration.MONTHS)
        with self.assertRaises(ValidationError):
            p.clean()

    def test_clean_rejects_unknown_tier(self):
        p = PromoCode(code='D2', percent_off=50, tiers=['gold'])
        with self.assertRaises(ValidationError):
            p.clean()

    def test_clean_catches_case_differing_duplicate_code(self):
        _code(code='LETO2026')
        dup = PromoCode(code='leto2026', percent_off=100)
        with self.assertRaises(ValidationError):
            dup.full_clean()

    def test_zero_percent_off_rejected_by_db_constraint(self):
        with self.assertRaises(IntegrityError):
            PromoCode.objects.create(code='ZERO', percent_off=0)


class PromoSubscriptionRowTests(TestCase):
    def setUp(self):
        _plans()
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')

    def _promo_sub(self, **kw):
        defaults = dict(
            user=self.user, tier=Tier.PREMIUM, status=Subscription.Status.ACTIVE,
            source=Subscription.Source.PROMO, stripe_customer_id='',
            stripe_subscription_id=None,
            current_period_end=timezone.now() + timedelta(days=30),
            grant_expires_at=None,
        )
        defaults.update(kw)
        return Subscription.objects.create(**defaults)

    def test_lifetime_promo_is_entitled_without_stripe_ids(self):
        self.assertTrue(self._promo_sub().is_entitled())

    def test_timed_promo_entitled_until_grant_expiry(self):
        sub = self._promo_sub(grant_expires_at=timezone.now() + timedelta(days=1))
        self.assertTrue(sub.is_entitled())
        sub.grant_expires_at = timezone.now() - timedelta(seconds=1)
        self.assertFalse(sub.is_entitled())

    def test_promo_quota_window_rolls_and_resets(self):
        sub = self._promo_sub(
            current_period_end=timezone.now() - timedelta(days=5),
            plans_used_this_period=30,
        )
        self.assertTrue(sub.within_monthly_quota())
        sub.refresh_from_db()
        self.assertEqual(sub.plans_used_this_period, 0)
        self.assertGreater(sub.current_period_end, timezone.now())
        self.assertLess(sub.current_period_end, timezone.now() + timedelta(days=30))

    def test_stripe_row_never_rolls(self):
        sub = Subscription.objects.create(
            user=self.user, tier=Tier.STANDARD, status=Subscription.Status.ACTIVE,
            stripe_customer_id='cus_1', stripe_subscription_id='sub_1',
            current_period_end=timezone.now() - timedelta(days=5),
            plans_used_this_period=7,
        )
        self.assertFalse(sub.within_monthly_quota())
        sub.refresh_from_db()
        self.assertEqual(sub.plans_used_this_period, 7)

    def test_two_promo_rows_with_null_stripe_id_allowed(self):
        self._promo_sub()
        other = User.objects.create_user('bob', 'b@x.com', 'pw')
        self._promo_sub(user=other)  # unique on stripe_subscription_id ignores NULLs
        self.assertEqual(Subscription.objects.filter(stripe_subscription_id=None).count(), 2)

    def test_promo_quota_window_rolls_multiple_windows(self):
        sub = self._promo_sub(
            current_period_end=timezone.now() - timedelta(days=65),
            plans_used_this_period=30,
        )
        self.assertTrue(sub.within_monthly_quota())
        sub.refresh_from_db()
        self.assertEqual(sub.plans_used_this_period, 0)
        self.assertGreater(sub.current_period_end, timezone.now() + timedelta(days=24))
        self.assertLess(sub.current_period_end, timezone.now() + timedelta(days=26))

    def test_promo_quota_window_rolls_from_null_and_persists(self):
        sub = self._promo_sub(current_period_end=None, plans_used_this_period=5)
        self.assertTrue(sub.within_monthly_quota())
        sub.refresh_from_db()
        self.assertIsNotNone(sub.current_period_end)
        self.assertGreater(sub.current_period_end, timezone.now())
        self.assertEqual(sub.plans_used_this_period, 0)

    def test_remaining_quota_also_rolls(self):
        sub = self._promo_sub(
            current_period_end=timezone.now() - timedelta(days=5),
            plans_used_this_period=30,
        )
        self.assertEqual(sub.remaining_quota(), 30)

    def test_canceled_promo_with_no_grant_expiry_not_entitled(self):
        sub = self._promo_sub(status=Subscription.Status.CANCELED, grant_expires_at=None)
        self.assertFalse(sub.is_entitled())


class NullableSubIdGuardTests(TestCase):
    """stripe_subscription_id is nullable now; webhook lookups must not treat a
    missing Stripe id as a match for `IS NULL` promo rows."""

    def setUp(self):
        _plans()
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')
        self.promo_sub = Subscription.objects.create(
            user=self.user, tier=Tier.PREMIUM, status=Subscription.Status.ACTIVE,
            source=Subscription.Source.PROMO, stripe_customer_id='',
            stripe_subscription_id=None,
            current_period_end=timezone.now() + timedelta(days=30),
        )

    def test_handle_payment_failed_ignores_missing_subscription_id(self):
        services.handle_payment_failed({'data': {'object': {'subscription': None}}})
        self.promo_sub.refresh_from_db()
        self.assertEqual(self.promo_sub.status, Subscription.Status.ACTIVE)

    def test_handle_subscription_deleted_ignores_missing_id(self):
        services.handle_subscription_deleted({'data': {'object': {'id': None}}})
        self.promo_sub.refresh_from_db()
        self.assertEqual(self.promo_sub.status, Subscription.Status.ACTIVE)


class EnsureStripeCouponTests(TestCase):
    def test_noop_for_100_percent(self):
        p = _code(percent_off=100)
        with patch('billing.services.stripe.Coupon.create') as create:
            self.assertIsNone(services.ensure_stripe_coupon(p))
        create.assert_not_called()
        self.assertEqual(p.stripe_coupon_id, '')

    @patch('billing.services.is_configured', return_value=False)
    def test_noop_when_unconfigured(self, _cfg):
        p = _code(percent_off=50)
        with patch('billing.services.stripe.Coupon.create') as create:
            self.assertIsNone(services.ensure_stripe_coupon(p))
        create.assert_not_called()

    @patch('billing.services.is_configured', return_value=True)
    def test_creates_forever_coupon(self, _cfg):
        p = _code(percent_off=50, duration_kind=PromoCode.Duration.LIFETIME)
        with patch('billing.services.stripe.Coupon.create', return_value={'id': 'cpn_1'}) as create:
            self.assertEqual(services.ensure_stripe_coupon(p), 'cpn_1')
        kw = create.call_args.kwargs
        self.assertEqual(kw['percent_off'], 50)
        self.assertEqual(kw['duration'], 'forever')
        self.assertEqual(kw['name'], 'LETO2026')
        self.assertEqual(kw['metadata'], {'promo_code_id': str(p.id)})
        p.refresh_from_db()
        self.assertEqual(p.stripe_coupon_id, 'cpn_1')

    @patch('billing.services.is_configured', return_value=True)
    def test_repeating_and_once(self, _cfg):
        p = _code(percent_off=20, duration_kind=PromoCode.Duration.MONTHS, duration_months=3)
        with patch('billing.services.stripe.Coupon.create', return_value={'id': 'cpn_r'}) as create:
            services.ensure_stripe_coupon(p)
        self.assertEqual(create.call_args.kwargs['duration'], 'repeating')
        self.assertEqual(create.call_args.kwargs['duration_in_months'], 3)
        q = _code(code='ONCE', percent_off=20, duration_kind=PromoCode.Duration.FIRST_INVOICE)
        with patch('billing.services.stripe.Coupon.create', return_value={'id': 'cpn_o'}) as create:
            services.ensure_stripe_coupon(q)
        self.assertEqual(create.call_args.kwargs['duration'], 'once')
        self.assertNotIn('duration_in_months', create.call_args.kwargs)

    @patch('billing.services.is_configured', return_value=True)
    def test_existing_id_is_kept(self, _cfg):
        p = _code(percent_off=50, stripe_coupon_id='cpn_keep')
        with patch('billing.services.stripe.Coupon.create') as create:
            self.assertEqual(services.ensure_stripe_coupon(p), 'cpn_keep')
        create.assert_not_called()
