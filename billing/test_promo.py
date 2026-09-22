"""
Promo code tests: model rules, validate/redeem endpoints, Stripe coupon sync,
webhook redemption recording, and precedence against Stripe subscriptions.
Stripe network calls are mocked throughout.
"""
from datetime import timedelta
from unittest.mock import patch

import stripe as stripe_lib
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import services
from . import promo as promo_svc
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


@override_settings(STRIPE_PRICE_STANDARD='price_std', STRIPE_PRICE_PREMIUM='price_prem',
                   FRONTEND_URL='https://app.test')
class CreateCheckoutSessionTests(TestCase):
    def setUp(self):
        _plans()
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')

    @patch('billing.services.get_or_create_customer', return_value='cus_1')
    @patch('billing.services.stripe.checkout.Session.create', return_value={'url': 'https://stripe/x'})
    def test_plain_checkout_allows_promotion_codes(self, create, _cust):
        url = services.create_checkout_session(self.user, 'standard')
        self.assertEqual(url, 'https://stripe/x')
        kw = create.call_args.kwargs
        self.assertTrue(kw['allow_promotion_codes'])
        self.assertNotIn('discounts', kw)
        self.assertEqual(kw['line_items'], [{'price': 'price_std', 'quantity': 1}])
        self.assertEqual(kw['metadata'], {'user_id': str(self.user.id), 'tier': 'standard'})
        self.assertEqual(kw['success_url'], 'https://app.test/billing/success?session_id={CHECKOUT_SESSION_ID}')
        self.assertEqual(kw['cancel_url'], 'https://app.test/pricing?sub=cancelled')

    @patch('billing.services.get_or_create_customer', return_value='cus_1')
    @patch('billing.services.stripe.checkout.Session.create', return_value={'url': 'https://stripe/y'})
    def test_promo_checkout_attaches_coupon(self, create, _cust):
        p = _code(percent_off=50, stripe_coupon_id='cpn_1')
        services.create_checkout_session(self.user, 'premium', promo=p)
        kw = create.call_args.kwargs
        self.assertEqual(kw['discounts'], [{'coupon': 'cpn_1'}])
        self.assertNotIn('allow_promotion_codes', kw)
        self.assertEqual(kw['metadata']['promo_code_id'], str(p.id))
        self.assertEqual(kw['subscription_data']['metadata']['promo_code_id'], str(p.id))

    def test_missing_price_raises(self):
        with override_settings(STRIPE_PRICE_STANDARD=''):
            SubscriptionPlan.objects.filter(tier='standard').update(stripe_price_id='')
            with self.assertRaises(services.PriceNotConfigured):
                services.create_checkout_session(self.user, 'standard')

    @patch('billing.services.get_or_create_customer', return_value='cus_1')
    @patch('billing.services.stripe.checkout.Session.create')
    def test_full_off_promo_without_coupon_raises(self, create, _cust):
        p = _code(percent_off=100)
        with self.assertRaises(services.PriceNotConfigured):
            services.create_checkout_session(self.user, 'premium', promo=p)
        create.assert_not_called()

    @patch('billing.services.is_configured', return_value=True)
    @patch('billing.services.get_or_create_customer', return_value='cus_1')
    @patch('billing.services.stripe.Coupon.create', return_value={'id': 'cpn_new'})
    @patch('billing.services.stripe.checkout.Session.create', return_value={'url': 'https://stripe/z'})
    def test_blank_coupon_is_minted_on_the_fly(self, sess, coupon, _cust, _cfg):
        p = _code(percent_off=50, stripe_coupon_id='')
        services.create_checkout_session(self.user, 'premium', promo=p)
        coupon.assert_called_once()
        self.assertEqual(sess.call_args.kwargs['discounts'], [{'coupon': 'cpn_new'}])
        p.refresh_from_db()
        self.assertEqual(p.stripe_coupon_id, 'cpn_new')


@override_settings(FRONTEND_URL='https://app.test')
class CheckoutViewTests(TestCase):
    def setUp(self):
        _plans()
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch('billing.views.services.create_checkout_session',
           side_effect=services.PriceNotConfigured('standard'))
    @patch('billing.views.is_configured', return_value=True)
    def test_price_not_configured_returns_503(self, _cfg, _create):
        resp = self.client.post('/api/billing/checkout/', {'tier': 'standard'})
        self.assertEqual(resp.status_code, 503)

    @patch('billing.views.services.create_checkout_session',
           side_effect=stripe_lib.error.StripeError('boom'))
    @patch('billing.views.is_configured', return_value=True)
    def test_stripe_error_returns_400(self, _cfg, _create):
        resp = self.client.post('/api/billing/checkout/', {'tier': 'standard'})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'Could not start checkout.')

    @patch('billing.views.services.create_checkout_session', return_value='https://stripe/ok')
    @patch('billing.views.is_configured', return_value=True)
    def test_success_returns_url(self, _cfg, _create):
        resp = self.client.post('/api/billing/checkout/', {'tier': 'standard'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {'url': 'https://stripe/ok'})


class ValidatePayloadTests(TestCase):
    def setUp(self):
        _plans()

    def test_unknown_code(self):
        self.assertEqual(promo_svc.validate_payload('nope'), {'valid': False, 'reason': 'not_found'})

    def test_blank_code(self):
        self.assertEqual(promo_svc.validate_payload('  '), {'valid': False, 'reason': 'not_found'})

    def test_expired_reason(self):
        _code(expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(promo_svc.validate_payload('leto2026')['reason'], 'expired')

    def test_valid_100_any_tier(self):
        _code()
        out = promo_svc.validate_payload('leto2026')
        self.assertTrue(out['valid'])
        self.assertEqual(out['code'], 'LETO2026')
        self.assertEqual(out['percent_off'], 100)
        self.assertEqual(out['duration_kind'], 'lifetime')
        self.assertIsNone(out['duration_months'])
        self.assertEqual(out['tiers'], [])
        self.assertEqual(out['prices'], {
            'standard': {'original': 99, 'discounted': 0},
            'premium': {'original': 199, 'discounted': 0},
        })

    def test_valid_half_premium_only(self):
        _code(code='HALF', percent_off=50, tiers=['premium'])
        out = promo_svc.validate_payload('HALF')
        self.assertEqual(out['prices'], {'premium': {'original': 199, 'discounted': 100}})

    def test_rounding(self):
        _code(code='T', percent_off=33, tiers=['standard'])
        self.assertEqual(promo_svc.validate_payload('T')['prices']['standard']['discounted'], 66)

    def test_half_up_rounding_values(self):
        self.assertEqual(promo_svc.discounted_price(197, 50), 99)
        self.assertEqual(promo_svc.discounted_price(99, 1), 98)
        self.assertEqual(promo_svc.discounted_price(99, 99), 1)
        self.assertEqual(promo_svc.discounted_price(199, 100), 0)

    def test_inactive_reason(self):
        _code(is_active=False)
        self.assertEqual(promo_svc.validate_payload('LETO2026')['reason'], 'inactive')

    def test_exhausted_reason(self):
        p = _code(max_redemptions=1)
        user = User.objects.create_user('bob', 'b@x.com', 'pw')
        PromoRedemption.objects.create(promo_code=p, user=user, tier='premium')
        self.assertEqual(promo_svc.validate_payload('LETO2026')['reason'], 'exhausted')

    def test_no_priced_tier_is_tier_not_allowed(self):
        SubscriptionPlan.objects.filter(tier='premium').update(is_active=False)
        _code(code='NOPLAN', tiers=['premium'])
        self.assertEqual(promo_svc.validate_payload('NOPLAN'),
                          {'valid': False, 'reason': 'tier_not_allowed'})


@override_settings(STRIPE_PRICE_STANDARD='price_std', STRIPE_PRICE_PREMIUM='price_prem',
                   FRONTEND_URL='https://app.test')
class RedeemTests(TestCase):
    def setUp(self):
        _plans()
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')

    def test_100_grants_lifetime_premium(self):
        p = _code()
        out = promo_svc.redeem(self.user, 'leto2026', 'premium')
        self.assertEqual(out, {'granted': True, 'tier': 'premium'})
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.source, Subscription.Source.PROMO)
        self.assertEqual(sub.tier, 'premium')
        self.assertIsNone(sub.stripe_subscription_id)
        self.assertEqual(sub.stripe_customer_id, '')
        self.assertIsNone(sub.grant_expires_at)
        self.assertEqual(sub.promo_code, p)
        self.assertEqual(sub.plans_used_this_period, 0)
        self.assertTrue(sub.is_entitled())
        self.assertEqual(PromoRedemption.objects.filter(promo_code=p, user=self.user, tier='premium').count(), 1)

    def test_100_timed_sets_grant_expiry(self):
        _code(duration_kind=PromoCode.Duration.MONTHS, duration_months=2)
        promo_svc.redeem(self.user, 'LETO2026', 'standard')
        sub = Subscription.objects.get(user=self.user)
        self.assertIsNotNone(sub.grant_expires_at)
        self.assertGreater(sub.grant_expires_at, timezone.now() + timedelta(days=55))

    def test_not_found(self):
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'X', 'premium')
        self.assertEqual(cm.exception.reason, 'not_found')

    def test_tier_not_allowed(self):
        _code(tiers=['premium'])
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'standard')
        self.assertEqual(cm.exception.reason, 'tier_not_allowed')

    def test_bad_tier_value(self):
        _code()
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'gold')
        self.assertEqual(cm.exception.reason, 'tier_not_allowed')

    def test_already_redeemed(self):
        _code()
        promo_svc.redeem(self.user, 'LETO2026', 'premium')
        Subscription.objects.filter(user=self.user).update(status=Subscription.Status.EXPIRED)
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'already_redeemed')

    def test_already_subscribed_stripe(self):
        _code()
        Subscription.objects.create(
            user=self.user, tier='standard', status=Subscription.Status.ACTIVE,
            stripe_customer_id='cus_1', stripe_subscription_id='sub_1',
            current_period_end=timezone.now() + timedelta(days=10),
        )
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'already_subscribed')

    def test_already_subscribed_stripe_past_due(self):
        _code()
        Subscription.objects.create(
            user=self.user, tier='standard', status=Subscription.Status.PAST_DUE,
            stripe_customer_id='cus_1', stripe_subscription_id='sub_pd',
            current_period_end=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'already_subscribed')

    def test_expired_stripe_row_is_replaced(self):
        _code()
        Subscription.objects.create(
            user=self.user, tier='standard', status=Subscription.Status.EXPIRED,
            stripe_customer_id='cus_1', stripe_subscription_id='sub_dead',
            current_period_end=timezone.now() - timedelta(days=1),
        )
        out = promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertTrue(out['granted'])
        sub = Subscription.objects.get(user=self.user)
        self.assertIsNone(sub.stripe_subscription_id)
        self.assertEqual(sub.source, Subscription.Source.PROMO)

    def test_already_subscribed_promo(self):
        _code()
        _code(code='OTHER')
        promo_svc.redeem(self.user, 'LETO2026', 'premium')
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'OTHER', 'premium')
        self.assertEqual(cm.exception.reason, 'already_subscribed')

    def test_expired_promo_row_is_replaced(self):
        _code()
        _code(code='OTHER')
        promo_svc.redeem(self.user, 'LETO2026', 'premium')
        Subscription.objects.filter(user=self.user).update(
            grant_expires_at=timezone.now() - timedelta(days=1))
        out = promo_svc.redeem(self.user, 'OTHER', 'standard')
        self.assertTrue(out['granted'])
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.tier, 'standard')
        self.assertTrue(sub.is_entitled())

    def test_exhausted_at_max(self):
        _code(max_redemptions=1)
        other = User.objects.create_user('bob', 'b@x.com', 'pw')
        promo_svc.redeem(other, 'LETO2026', 'premium')
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'exhausted')
        self.assertFalse(Subscription.objects.filter(user=self.user).exists())

    def test_inactive_reason(self):
        _code(is_active=False)
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'inactive')

    @patch('billing.services.is_configured', return_value=True)
    @patch('billing.services.create_checkout_session', return_value='https://stripe/z')
    def test_percent_returns_checkout_url_without_redemption(self, create, _cfg):
        p = _code(percent_off=50, stripe_coupon_id='cpn_1')
        out = promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(out, {'granted': False, 'url': 'https://stripe/z'})
        create.assert_called_once_with(self.user, 'premium', promo=p)
        self.assertFalse(PromoRedemption.objects.exists())
        self.assertFalse(Subscription.objects.filter(user=self.user).exists())

    @patch('billing.services.is_configured', return_value=False)
    def test_percent_unconfigured_stripe_is_stripe_error(self, _cfg):
        _code(percent_off=50, stripe_coupon_id='cpn_1')
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'stripe_error')

    @patch('billing.services.is_configured', return_value=True)
    @patch('billing.services.create_checkout_session',
           side_effect=services.PriceNotConfigured('x'))
    def test_percent_price_not_configured_is_stripe_error(self, _create, _cfg):
        _code(percent_off=50, stripe_coupon_id='cpn_1')
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'stripe_error')

    @patch('billing.services.is_configured', return_value=True)
    @patch('billing.services.create_checkout_session',
           side_effect=stripe_lib.error.StripeError('boom'))
    def test_percent_stripe_error_is_stripe_error(self, _create, _cfg):
        _code(percent_off=50, stripe_coupon_id='cpn_1')
        with self.assertRaises(promo_svc.RedeemError) as cm:
            promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(cm.exception.reason, 'stripe_error')

    def test_rollback_on_redemption_write_failure(self):
        _code()
        with patch.object(PromoRedemption.objects, 'create', side_effect=IntegrityError('x')):
            with self.assertRaises(IntegrityError):
                promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertFalse(Subscription.objects.filter(user=self.user).exists())

    def test_tier_locked_code_grants_allowed_tier(self):
        _code(tiers=['premium'])
        out = promo_svc.redeem(self.user, 'LETO2026', 'premium')
        self.assertEqual(out, {'granted': True, 'tier': 'premium'})

    def test_code_with_surrounding_whitespace_grants(self):
        _code()
        out = promo_svc.redeem(self.user, '  leto2026 ', 'premium')
        self.assertEqual(out, {'granted': True, 'tier': 'premium'})


class RecordCheckoutRedemptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')

    def test_records_once(self):
        p = _code(percent_off=50)
        session = {'id': 'cs_9', 'metadata': {'user_id': str(self.user.id), 'tier': 'standard',
                                              'promo_code_id': str(p.id)}}
        promo_svc.record_checkout_redemption(session)
        promo_svc.record_checkout_redemption(session)
        reds = PromoRedemption.objects.filter(promo_code=p, user=self.user)
        self.assertEqual(reds.count(), 1)
        self.assertEqual(reds[0].tier, 'standard')
        self.assertEqual(reds[0].stripe_checkout_session_id, 'cs_9')

    def test_ignores_sessions_without_promo(self):
        promo_svc.record_checkout_redemption({'id': 'cs_1', 'metadata': {'user_id': str(self.user.id)}})
        promo_svc.record_checkout_redemption({'id': 'cs_2', 'metadata': {'promo_code_id': '999999', 'user_id': str(self.user.id)}})
        self.assertFalse(PromoRedemption.objects.exists())


class PrecedenceAndWebhookTests(TestCase):
    def setUp(self):
        _plans()
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')

    def _stripe_sub_obj(self, sub_id='sub_1'):
        return {
            'id': sub_id, 'status': 'active', 'customer': 'cus_1',
            'current_period_end': int((timezone.now() + timedelta(days=30)).timestamp()),
            'cancel_at_period_end': False,
            'items': {'data': [{'price': {'id': 'price_std'}}]},
            'metadata': {'user_id': str(self.user.id), 'tier': 'standard'},
        }

    def test_paid_subscription_overwrites_promo_row(self):
        p = _code()
        promo_svc.redeem(self.user, 'LETO2026', 'premium')
        services.upsert_subscription(self.user, self._stripe_sub_obj(), 'cus_1', tier='standard')
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.source, Subscription.Source.STRIPE)
        self.assertIsNone(sub.grant_expires_at)
        self.assertEqual(sub.stripe_subscription_id, 'sub_1')
        self.assertEqual(sub.tier, 'standard')
        self.assertEqual(sub.promo_code, p)  # audit link kept

    @patch('billing.services.stripe.Subscription.retrieve')
    def test_checkout_completed_records_promo_redemption_once(self, retrieve):
        p = _code(percent_off=50, stripe_coupon_id='cpn_1')
        retrieve.return_value = self._stripe_sub_obj()
        event = {'data': {'object': {
            'id': 'cs_9', 'mode': 'subscription', 'customer': 'cus_1', 'subscription': 'sub_1',
            'metadata': {'user_id': str(self.user.id), 'tier': 'standard', 'promo_code_id': str(p.id)},
        }}}
        with patch('billing.services.track_paid'):
            services.handle_checkout_completed(event)
            services.handle_checkout_completed(event)
        reds = PromoRedemption.objects.filter(promo_code=p, user=self.user)
        self.assertEqual(reds.count(), 1)
        self.assertEqual(reds[0].stripe_checkout_session_id, 'cs_9')
        self.assertEqual(reds[0].tier, 'standard')
        self.assertEqual(Subscription.objects.get(user=self.user).source, Subscription.Source.STRIPE)

    @patch('billing.services.stripe.Subscription.retrieve')
    def test_checkout_completed_without_promo_records_nothing(self, retrieve):
        retrieve.return_value = self._stripe_sub_obj()
        event = {'data': {'object': {
            'id': 'cs_1', 'mode': 'subscription', 'customer': 'cus_1', 'subscription': 'sub_1',
            'metadata': {'user_id': str(self.user.id), 'tier': 'standard'},
        }}}
        with patch('billing.services.track_paid'):
            services.handle_checkout_completed(event)
        self.assertFalse(PromoRedemption.objects.exists())

    @patch('billing.services.is_configured', return_value=False)
    def test_cancel_skips_stripe_for_promo_rows(self, _cfg):
        _code()
        promo_svc.redeem(self.user, 'LETO2026', 'premium')
        with patch('billing.services.stripe.Subscription.cancel') as cancel:
            services.cancel_subscription_for_user(self.user)  # must not raise
        cancel.assert_not_called()


@override_settings(STRIPE_PRICE_STANDARD='price_std', STRIPE_PRICE_PREMIUM='price_prem',
                   FRONTEND_URL='https://app.test', ALLOWED_HOSTS=['testserver'])
class PromoApiTests(TestCase):
    def setUp(self):
        _plans()
        self.user = User.objects.create_user('ann', 'a@x.com', 'pw')
        self.client = APIClient()

    def test_validate_is_public_and_always_200(self):
        r = self.client.get('/api/billing/promo/validate/', {'code': 'nope'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'valid': False, 'reason': 'not_found'})

    def test_validate_valid(self):
        _code()
        r = self.client.get('/api/billing/promo/validate/', {'code': 'leto2026'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['valid'])
        self.assertEqual(r.json()['prices']['premium']['discounted'], 0)

    def test_redeem_requires_auth(self):
        r = self.client.post('/api/billing/promo/redeem/', {'code': 'X', 'tier': 'premium'})
        self.assertEqual(r.status_code, 401)

    def test_redeem_grant(self):
        _code()
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/billing/promo/redeem/', {'code': 'leto2026', 'tier': 'premium'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'granted': True, 'tier': 'premium'})
        me = self.client.get('/api/billing/me/').json()
        self.assertEqual(me['subscription']['source'], 'promo')
        self.assertIsNone(me['subscription']['grant_expires_at'])
        self.assertTrue(me['subscription']['entitled'])

    def test_redeem_error_shape(self):
        _code(tiers=['premium'])
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/billing/promo/redeem/', {'code': 'LETO2026', 'tier': 'standard'})
        self.assertEqual(r.status_code, 400)
        body = r.json()
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['reason'], 'tier_not_allowed')
        self.assertIn('tarif', body['error'])

    @patch('billing.promo.services.is_configured', return_value=True)
    @patch('billing.promo.services.create_checkout_session', return_value='https://stripe/q')
    def test_redeem_percent_returns_url(self, _create, _cfg):
        _code(percent_off=30, stripe_coupon_id='cpn_1')
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/billing/promo/redeem/', {'code': 'LETO2026', 'tier': 'standard'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'granted': False, 'url': 'https://stripe/q'})

    @patch('billing.promo.services.is_configured', return_value=True)
    @patch('billing.promo.services.create_checkout_session', side_effect=stripe_lib.error.StripeError('x'))
    def test_redeem_percent_stripe_failure_is_400(self, _create, _cfg):
        _code(percent_off=30, stripe_coupon_id='cpn_1')
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/billing/promo/redeem/', {'code': 'LETO2026', 'tier': 'standard'})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['reason'], 'stripe_error')
