"""
Billing models — Stripe-backed subscriptions.

Architecture (see docs/stripe-billing-plan.md §2):
- Stripe is the system of record for *billing* (charges, dunning, card updates).
- Django is the system of record for *entitlement*: the `Subscription` row below
  is what the generation gate checks. Django never runs a billing clock; it only
  reacts to Stripe webhooks and flips this row.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Tier(models.TextChoices):
    STANDARD = 'standard', 'Standard'
    PREMIUM = 'premium', 'Premium'


class SubscriptionPlan(models.Model):
    """
    Tier configuration — source of truth for both the pricing page (served via
    GET /api/billing/plans/) and the quota gate. Replaces the hardcoded PLANS
    array in frontend/src/pages/Pricing.tsx. Seeded via data migration.
    """
    tier = models.CharField(
        max_length=20, choices=Tier.choices, unique=True,
        help_text="Matches Stripe metadata + the entitlement tier.",
    )
    name = models.CharField(max_length=100, help_text="Display name, e.g. 'Eatalníček Standard'.")
    price_czk = models.PositiveIntegerField(help_text="Monthly price in CZK (display + sanity check).")
    stripe_price_id = models.CharField(
        max_length=255, blank=True,
        help_text="Stripe recurring Price ID (price_…). Test and live differ; set per environment.",
    )
    monthly_plan_quota = models.PositiveIntegerField(
        help_text="Meal plans generatable per billing period (Standard 7, Premium 30).",
    )
    edits_per_plan = models.PositiveIntegerField(
        help_text="Allowed edits per generated plan (Standard 10, Premium 5).",
    )
    allow_multi_store = models.BooleanField(
        default=False, help_text="Multi-store price optimization (Premium only).",
    )
    is_active = models.BooleanField(default=True, help_text="Show on the pricing page.")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order']
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'

    def __str__(self):
        return f"{self.name} ({self.price_czk} CZK/mo)"


class Subscription(models.Model):
    """
    User-level, time-bounded entitlement. One per user (the active one).
    Mirrored from Stripe via webhooks; `current_period_end` is the entitlement
    expiry the gate enforces.
    """
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAST_DUE = 'past_due', 'Past due'
        CANCELED = 'canceled', 'Canceled'
        EXPIRED = 'expired', 'Expired'

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='subscription',
    )
    tier = models.CharField(max_length=20, choices=Tier.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True,
    )
    stripe_customer_id = models.CharField(max_length=255, db_index=True)
    stripe_subscription_id = models.CharField(
        max_length=255, unique=True, db_index=True,
        help_text="Stripe Subscription ID (sub_…). Webhook idempotency anchor.",
    )
    current_period_end = models.DateTimeField(
        null=True, blank=True, help_text="From Stripe; the entitlement expiry.",
    )
    cancel_at_period_end = models.BooleanField(
        default=False, help_text="Set when the user cancels via the Customer Portal.",
    )
    plans_used_this_period = models.PositiveIntegerField(
        default=0, help_text="Reset to 0 on each renewal (invoice.paid).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'

    def __str__(self):
        return f"{self.user.username} — {self.get_tier_display()} ({self.status})"

    @property
    def plan(self) -> 'SubscriptionPlan | None':
        return SubscriptionPlan.objects.filter(tier=self.tier).first()

    def is_entitled(self) -> bool:
        """Active status AND not past the paid period."""
        if self.status != self.Status.ACTIVE:
            return False
        if self.current_period_end is None:
            return False
        return self.current_period_end > timezone.now()

    def within_monthly_quota(self) -> bool:
        """True if the user still has plan generations left this period."""
        plan = self.plan
        if plan is None:
            return False
        return self.plans_used_this_period < plan.monthly_plan_quota

    def remaining_quota(self) -> int:
        plan = self.plan
        if plan is None:
            return 0
        return max(0, plan.monthly_plan_quota - self.plans_used_this_period)


class StripeCustomer(models.Model):
    """
    Maps a Django user to their Stripe Customer id. Exists independently of
    Subscription so we can get-or-create the customer at checkout time, before
    any subscription has been provisioned (and reuse it across re-attempts).
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='stripe_customer',
    )
    stripe_customer_id = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stripe Customer'
        verbose_name_plural = 'Stripe Customers'

    def __str__(self):
        return f"{self.user.username} → {self.stripe_customer_id}"


class ProcessedWebhookEvent(models.Model):
    """
    Idempotency ledger for Stripe webhooks. Stripe retries on any non-2xx, so
    every handler checks/inserts the event id here before mutating state. The
    unique constraint makes double-delivery a no-op.
    """
    stripe_event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=100)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Processed Webhook Event'
        verbose_name_plural = 'Processed Webhook Events'

    def __str__(self):
        return f"{self.event_type} ({self.stripe_event_id})"
