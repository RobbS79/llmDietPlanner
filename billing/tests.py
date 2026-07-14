"""
Tests for the billing app: entitlement gate + Stripe webhook handling.

These cover the parts that can't wait for live Stripe: the allow/deny logic the
generation gate depends on, and the webhook's signature verification, idempotency,
and provisioning (Stripe network calls are mocked).
"""
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from . import services
from .entitlements import allow_generation, active_subscription
from .models import (
    Subscription, SubscriptionPlan, Tier, ProcessedWebhookEvent, StripeCustomer,
)
from analytics.models import MarketingAttribution
import stripe as stripe_lib


def _make_sub(user, *, status=Subscription.Status.ACTIVE, period_days=15,
              tier=Tier.STANDARD, used=0):
    return Subscription.objects.create(
        user=user, tier=tier, status=status,
        stripe_customer_id='cus_test', stripe_subscription_id=f'sub_{user.id}',
        current_period_end=timezone.now() + timedelta(days=period_days),
        plans_used_this_period=used,
    )


class EntitlementTests(TestCase):
    def setUp(self):
        # plans seeded by migration 0002; ensure present for isolated test DB
        SubscriptionPlan.objects.get_or_create(
            tier=Tier.STANDARD, defaults=dict(
                name='Standard', price_czk=99, monthly_plan_quota=7,
                edits_per_plan=10, allow_multi_store=False),
        )
        self.user = User.objects.create_user('alice', 'a@x.com', 'pw')

    def test_free_user_allowed(self):
        # default profile gives 2 free generations
        self.assertTrue(allow_generation(self.user))

    def test_no_free_no_sub_denied(self):
        self.user.profile.free_generations_remaining = 0
        self.user.profile.save()
        self.assertFalse(allow_generation(self.user))

    def test_active_sub_within_quota_allowed(self):
        self.user.profile.free_generations_remaining = 0
        self.user.profile.save()
        _make_sub(self.user, used=0)
        self.assertTrue(allow_generation(self.user))

    def test_active_sub_quota_exhausted_denied(self):
        self.user.profile.free_generations_remaining = 0
        self.user.profile.save()
        _make_sub(self.user, used=7)  # quota is 7
        self.assertFalse(allow_generation(self.user))

    def test_expired_sub_not_entitled(self):
        sub = _make_sub(self.user, period_days=-1)  # already past
        self.assertIsNone(active_subscription(self.user))
        # still has free credits, so generation allowed via free path
        self.assertTrue(allow_generation(self.user))

    def test_past_due_not_entitled(self):
        _make_sub(self.user, status=Subscription.Status.PAST_DUE)
        self.assertIsNone(active_subscription(self.user))


class CustomerSelfHealTests(TestCase):
    """get_or_create_customer must not hand checkout a stale/invalid id."""

    def setUp(self):
        self.user = User.objects.create_user('carol', 'c@x.com', 'pw')

    @patch('billing.services.stripe.Customer.retrieve')
    def test_usable_existing_customer_is_reused(self, mock_retrieve):
        StripeCustomer.objects.create(user=self.user, stripe_customer_id='cus_live_ok')
        mock_retrieve.return_value = {'id': 'cus_live_ok', 'deleted': False}
        with patch('billing.services.stripe.Customer.create') as mock_create:
            cid = services.get_or_create_customer(self.user)
        self.assertEqual(cid, 'cus_live_ok')
        mock_create.assert_not_called()

    @patch('billing.services.stripe.Customer.retrieve')
    def test_stale_customer_is_replaced(self, mock_retrieve):
        # leftover test-mode id that the live key can't resolve
        StripeCustomer.objects.create(user=self.user, stripe_customer_id='cus_stale_test')
        mock_retrieve.side_effect = stripe_lib.error.InvalidRequestError(
            "No such customer: 'cus_stale_test'", param='customer',
        )
        with patch('billing.services.stripe.Customer.create') as mock_create:
            mock_create.return_value = {'id': 'cus_fresh_live'}
            cid = services.get_or_create_customer(self.user)
        self.assertEqual(cid, 'cus_fresh_live')
        mock_create.assert_called_once()
        # mapping overwritten with the fresh id
        self.assertEqual(
            StripeCustomer.objects.get(user=self.user).stripe_customer_id,
            'cus_fresh_live',
        )


def _sign(payload: str, secret: str) -> str:
    ts = int(time.time())
    signed = f"{ts}.{payload}".encode()
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


@override_settings(
    STRIPE_WEBHOOK_SECRET='whsec_test_secret',
    STRIPE_PRICE_STANDARD='price_standard_test',
    ALLOWED_HOSTS=['testserver', 'localhost'],
)
class WebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        SubscriptionPlan.objects.get_or_create(
            tier=Tier.STANDARD, defaults=dict(
                name='Standard', price_czk=99, monthly_plan_quota=7,
                edits_per_plan=10, allow_multi_store=False),
        )
        self.user = User.objects.create_user('bob', 'b@x.com', 'pw')

    def _checkout_event(self, event_id='evt_1'):
        return json.dumps({
            'id': event_id,
            'object': 'event',
            'type': 'checkout.session.completed',
            'data': {'object': {
                'id': 'cs_1', 'mode': 'subscription', 'customer': 'cus_1',
                'subscription': 'sub_1',
                'metadata': {'user_id': str(self.user.id), 'tier': 'standard'},
            }},
        })

    def _post(self, payload):
        return self.client.post(
            '/api/billing/webhook/', data=payload, content_type='application/json',
            HTTP_STRIPE_SIGNATURE=_sign(payload, 'whsec_test_secret'),
        )

    def test_bad_signature_rejected(self):
        payload = self._checkout_event()
        r = self.client.post(
            '/api/billing/webhook/', data=payload, content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=deadbeef',
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Subscription.objects.exists())

    @patch('billing.services.stripe.Subscription.retrieve')
    def test_checkout_provisions_subscription(self, mock_retrieve):
        mock_retrieve.return_value = {
            'id': 'sub_1', 'status': 'active', 'cancel_at_period_end': False,
            'current_period_end': int(time.time()) + 30 * 86400,
            'items': {'data': [{'price': {'id': 'price_standard_test'}}]},
        }
        r = self._post(self._checkout_event())
        self.assertEqual(r.status_code, 200)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.tier, Tier.STANDARD)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertTrue(sub.is_entitled())

    @patch('billing.services.stripe.Subscription.retrieve')
    def test_duplicate_event_is_noop(self, mock_retrieve):
        mock_retrieve.return_value = {
            'id': 'sub_1', 'status': 'active', 'cancel_at_period_end': False,
            'current_period_end': int(time.time()) + 30 * 86400,
            'items': {'data': [{'price': {'id': 'price_standard_test'}}]},
        }
        payload = self._checkout_event(event_id='evt_dup')
        self.assertEqual(self._post(payload).status_code, 200)
        self.assertEqual(self._post(payload).status_code, 200)
        # handler ran once; second delivery short-circuited on idempotency
        self.assertEqual(mock_retrieve.call_count, 1)
        self.assertEqual(ProcessedWebhookEvent.objects.count(), 1)
        self.assertEqual(Subscription.objects.filter(user=self.user).count(), 1)

    def _subscription_event(self, *, event_type, event_id, metadata=None,
                            customer='cus_1', status='active'):
        """A customer.subscription.* event whose object IS the subscription
        (price embedded in items — handlers read it without a retrieve call)."""
        return json.dumps({
            'id': event_id,
            'object': 'event',
            'type': event_type,
            'data': {'object': {
                'id': 'sub_1', 'status': status, 'customer': customer,
                'cancel_at_period_end': False,
                'current_period_end': int(time.time()) + 30 * 86400,
                'metadata': metadata or {},
                'items': {'data': [{'price': {'id': 'price_standard_test'}}]},
            }},
        })

    def test_subscription_updated_creates_if_missing(self):
        """Out-of-order delivery: an `updated` event arrives with no existing
        row (the `checkout.session.completed` never reached us). It must still
        provision rather than silently drop — that's the revenue bug."""
        payload = self._subscription_event(
            event_type='customer.subscription.updated', event_id='evt_upd',
            metadata={'user_id': str(self.user.id)},
        )
        self.assertEqual(self._post(payload).status_code, 200)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.tier, Tier.STANDARD)
        self.assertTrue(sub.is_entitled())

    def test_subscription_created_provisions_via_customer_mapping(self):
        """A `customer.subscription.created` (e.g. dashboard-made sub) with no
        metadata still provisions when a StripeCustomer mapping exists."""
        StripeCustomer.objects.create(user=self.user, stripe_customer_id='cus_1')
        payload = self._subscription_event(
            event_type='customer.subscription.created', event_id='evt_cre',
        )
        self.assertEqual(self._post(payload).status_code, 200)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.tier, Tier.STANDARD)
        self.assertTrue(sub.is_entitled())

    def test_subscription_updated_preserves_usage(self):
        """An `updated` event must NOT reset plans_used_this_period (only a
        renewal `invoice.paid` does) — otherwise every Stripe tweak refunds
        the user's monthly quota."""
        Subscription.objects.create(
            user=self.user, tier=Tier.STANDARD, status=Subscription.Status.ACTIVE,
            stripe_customer_id='cus_1', stripe_subscription_id='sub_1',
            current_period_end=timezone.now() + timedelta(days=10),
            plans_used_this_period=5,
        )
        payload = self._subscription_event(
            event_type='customer.subscription.updated', event_id='evt_upd2',
            metadata={'user_id': str(self.user.id)},
        )
        self.assertEqual(self._post(payload).status_code, 200)
        self.user.subscription.refresh_from_db()
        self.assertEqual(self.user.subscription.plans_used_this_period, 5)


@override_settings(STRIPE_PRICE_STANDARD='price_standard_test')
class ReconcileCommandTests(TestCase):
    """The operational lever: bind a Stripe subscription to a Django user when
    webhooks failed or the sub was made outside checkout (no metadata)."""

    def setUp(self):
        SubscriptionPlan.objects.get_or_create(
            tier=Tier.STANDARD, defaults=dict(
                name='Standard', price_czk=99, monthly_plan_quota=7,
                edits_per_plan=10, allow_multi_store=False),
        )
        self.user = User.objects.create_user('carol', 'c@x.com', 'pw')

    def _stripe_sub(self):
        return {
            'id': 'sub_orphan', 'status': 'active', 'customer': 'cus_orphan',
            'cancel_at_period_end': False,
            'current_period_end': int(time.time()) + 20 * 86400,
            'metadata': {},  # the real-world broken case: no user_id
            'items': {'data': [{'price': {'id': 'price_standard_test'}}]},
        }

    @patch('billing.services.stripe.Subscription.retrieve')
    def test_reconcile_by_email_provisions(self, mock_retrieve):
        mock_retrieve.return_value = self._stripe_sub()
        call_command('reconcile_subscription', 'sub_orphan', '--email', 'c@x.com')
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.stripe_subscription_id, 'sub_orphan')
        self.assertEqual(sub.tier, Tier.STANDARD)
        self.assertTrue(sub.is_entitled())
        # customer mapping is recorded for future webhook resolution
        self.assertTrue(
            StripeCustomer.objects.filter(
                user=self.user, stripe_customer_id='cus_orphan').exists()
        )

    @patch('billing.services.stripe.Subscription.retrieve')
    def test_reconcile_unknown_user_errors(self, mock_retrieve):
        mock_retrieve.return_value = self._stripe_sub()
        with self.assertRaises(CommandError):
            call_command('reconcile_subscription', 'sub_orphan',
                         '--email', 'nobody@x.com')


class PaidEventTests(TestCase):
    """checkout.session.completed must fire the server-side Purchase CAPI
    event, priced from the tier's SubscriptionPlan, once provisioning
    succeeds. track_paid is consent-gated itself, so this handler doesn't
    need to check consent — it just needs to call it exactly once, with the
    right value, on the success path."""

    def setUp(self):
        self.plan, _ = SubscriptionPlan.objects.update_or_create(
            tier=Tier.STANDARD, defaults=dict(
                name='Standard', price_czk=99,
                stripe_price_id='price_standard_test', monthly_plan_quota=7,
                edits_per_plan=10, allow_multi_store=False,
            ),
        )
        self.user = User.objects.create_user('buyer', 'buyer@x.com', 'pw')
        MarketingAttribution.objects.create(user=self.user, marketing_consent=True)

    def _event(self):
        return {'data': {'object': {
            'id': 'cs_1', 'mode': 'subscription', 'customer': 'cus_1',
            'subscription': 'sub_1',
            'metadata': {'user_id': str(self.user.id), 'tier': Tier.STANDARD},
        }}}

    @patch('billing.services._send_welcome_email')
    @patch('billing.services.upsert_subscription')
    @patch('billing.services.stripe.Subscription.retrieve')
    @patch('billing.services.track_paid')
    def test_checkout_completed_fires_paid_with_tier_price(
        self, mock_paid, mock_retrieve, mock_upsert, mock_welcome,
    ):
        mock_retrieve.return_value = {
            'id': 'sub_1', 'status': 'active',
            'items': {'data': [{'price': {'id': 'price_standard_test'}}]},
        }
        mock_upsert.return_value = object()  # non-None => provisioned
        services.handle_checkout_completed(self._event())
        mock_paid.assert_called_once()
        self.assertEqual(mock_paid.call_args.args[0], self.user)
        self.assertEqual(mock_paid.call_args.kwargs['value'], 99)
        self.assertEqual(mock_paid.call_args.kwargs['currency'], 'CZK')

    @patch('billing.services._send_welcome_email')
    @patch('billing.services.upsert_subscription')
    @patch('billing.services.stripe.Subscription.retrieve')
    @patch('billing.services.track_paid')
    def test_paid_not_fired_when_provisioning_fails(
        self, mock_paid, mock_retrieve, mock_upsert, mock_welcome,
    ):
        """upsert_subscription returning None (unknown tier etc.) means we
        never provisioned — must not report a purchase for it."""
        mock_retrieve.return_value = {
            'id': 'sub_1', 'status': 'active',
            'items': {'data': [{'price': {'id': 'price_standard_test'}}]},
        }
        mock_upsert.return_value = None
        services.handle_checkout_completed(self._event())
        mock_paid.assert_not_called()
