"""
Billing models — Stripe-backed subscriptions.

Architecture (see docs/stripe-billing-plan.md §2):
- Stripe is the system of record for *billing* (charges, dunning, card updates).
- Django is the system of record for *entitlement*: the `Subscription` row below
  is what the generation gate checks. Django never runs a billing clock; it only
  reacts to Stripe webhooks and flips this row.
"""
import calendar
from datetime import timedelta

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Tier(models.TextChoices):
    STANDARD = 'standard', 'Standard'
    PREMIUM = 'premium', 'Premium'


PROMO_QUOTA_WINDOW = timedelta(days=30)


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
    name = models.CharField(max_length=100, help_text="Display name, e.g. 'Vařto Standard'.")
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

    class Source(models.TextChoices):
        STRIPE = 'stripe', 'Stripe'
        PROMO = 'promo', 'Promo kód'

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='subscription',
    )
    tier = models.CharField(max_length=20, choices=Tier.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True,
    )
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.STRIPE, db_index=True,
        help_text="promo rows have no Stripe ids and expire via grant_expires_at.",
    )
    stripe_customer_id = models.CharField(max_length=255, db_index=True, blank=True)
    stripe_subscription_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True, db_index=True,
        help_text="Stripe Subscription ID (sub_…). Webhook idempotency anchor. NULL for promo grants.",
    )
    current_period_end = models.DateTimeField(
        null=True, blank=True,
        help_text="Stripe rows: entitlement expiry from Stripe. Promo rows: rolling 30-day quota window.",
    )
    cancel_at_period_end = models.BooleanField(
        default=False, help_text="Set when the user cancels via the Customer Portal.",
    )
    plans_used_this_period = models.PositiveIntegerField(
        default=0, help_text="Reset to 0 on each renewal (invoice.paid).",
    )
    grant_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Promo rows only. NULL = lifetime.",
    )
    promo_code = models.ForeignKey(
        'PromoCode', null=True, blank=True, on_delete=models.SET_NULL, related_name='subscriptions',
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
        """Active status AND not past the paid period (Stripe) / grant expiry (promo)."""
        if self.status != self.Status.ACTIVE:
            return False
        if self.source == self.Source.PROMO:
            return self.grant_expires_at is None or self.grant_expires_at > timezone.now()
        if self.current_period_end is None:
            return False
        return self.current_period_end > timezone.now()

    def _roll_quota_window_if_due(self) -> None:
        """Promo rows have no invoice.paid to reset usage; roll a 30-day window lazily.

        Rolls via a conditional UPDATE keyed on the previously-read
        current_period_end, so two concurrent readers hitting the same stale
        window can't each independently reset the counter (last write wins
        silently). Whichever writer the DB accepts wins; both then refresh
        from the DB so the caller sees the winner's state.
        """
        if self.source != self.Source.PROMO:
            return
        now = timezone.now()
        old_end = self.current_period_end
        if old_end is None:
            Subscription.objects.filter(
                pk=self.pk, current_period_end__isnull=True,
            ).update(
                current_period_end=now + PROMO_QUOTA_WINDOW,
                plans_used_this_period=0,
                updated_at=timezone.now(),
            )
            self.refresh_from_db(fields=['current_period_end', 'plans_used_this_period'])
            return
        if old_end > now:
            return
        new_end = old_end
        while new_end <= now:
            new_end += PROMO_QUOTA_WINDOW
        Subscription.objects.filter(
            pk=self.pk, current_period_end=old_end,
        ).update(
            current_period_end=new_end,
            plans_used_this_period=0,
            updated_at=timezone.now(),
        )
        self.refresh_from_db(fields=['current_period_end', 'plans_used_this_period'])

    def within_monthly_quota(self) -> bool:
        """True if the user still has plan generations left this period."""
        plan = self.plan
        if plan is None:
            return False
        self._roll_quota_window_if_due()
        return self.plans_used_this_period < plan.monthly_plan_quota

    def remaining_quota(self) -> int:
        plan = self.plan
        if plan is None:
            return 0
        self._roll_quota_window_if_due()
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


def _add_months(dt, months: int):
    """Calendar month addition, clamping the day (Jan 31 + 1 → Feb 28)."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


class PromoCode(models.Model):
    """
    Admin-defined discount code. 100 % codes grant a Subscription row directly
    (no Stripe, no card); 1–99 % codes are mirrored to a Stripe Coupon that is
    attached to Checkout. Expiry and max uses are enforced here, never in Stripe.
    """
    class Duration(models.TextChoices):
        LIFETIME = 'lifetime', 'Navždy'
        MONTHS = 'months', 'N měsíců'
        FIRST_INVOICE = 'first_invoice', 'Jen první platba / 1 měsíc'

    code = models.CharField(max_length=40, unique=True, help_text="Ukládá se velkými písmeny.")
    percent_off = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="1–100. 100 = zdarma bez karty.",
    )
    duration_kind = models.CharField(max_length=20, choices=Duration.choices, default=Duration.LIFETIME)
    duration_months = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Jen pro 'N měsíců'.",
    )
    tiers = models.JSONField(
        default=list, blank=True,
        help_text='Seznam povolených tarifů, např. ["premium"]. Prázdné = libovolný.',
    )
    max_redemptions = models.PositiveIntegerField(
        null=True, blank=True, help_text="Prázdné = neomezeně.",
    )
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Prázdné = nikdy.")
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True, help_text="Interní poznámka (komu, kampaň).")
    stripe_coupon_id = models.CharField(
        max_length=255, blank=True,
        help_text="Vyplní se automaticky pro kódy pod 100 %.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Promo kód'
        verbose_name_plural = 'Promo kódy'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(percent_off__gte=1, percent_off__lte=100),
                name='promocode_percent_off_1_100',
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.percent_off} %)"

    @staticmethod
    def normalise(raw: str) -> str:
        return (raw or '').strip().upper()

    def save(self, *args, **kwargs):
        self.code = self.normalise(self.code)
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        self.code = self.normalise(self.code)
        if self.duration_kind == self.Duration.MONTHS and not self.duration_months:
            raise ValidationError({'duration_months': 'Zadejte počet měsíců.'})
        bad = [t for t in (self.tiers or []) if t not in Tier.values]
        if bad:
            raise ValidationError({'tiers': f'Neznámé tarify: {bad}'})

    def redemption_count(self) -> int:
        return self.redemptions.count()

    def allows_tier(self, tier: str) -> bool:
        return not self.tiers or tier in self.tiers

    def check_redeemable(self, now=None) -> str | None:
        """None if redeemable, else 'inactive' | 'expired' | 'exhausted'."""
        now = now or timezone.now()
        if not self.is_active:
            return 'inactive'
        if self.expires_at is not None and self.expires_at <= now:
            return 'expired'
        if self.max_redemptions is not None and self.redemption_count() >= self.max_redemptions:
            return 'exhausted'
        return None

    def grant_expiry(self, now):
        """When a 100 % grant made now stops entitling; None = lifetime."""
        if self.duration_kind == self.Duration.LIFETIME:
            return None
        if self.duration_kind == self.Duration.MONTHS:
            return _add_months(now, self.duration_months or 1)
        return _add_months(now, 1)


class PromoRedemption(models.Model):
    """One row per (code, user). This table IS the max_redemptions counter."""
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name='redemptions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_redemptions')
    tier = models.CharField(max_length=20, choices=Tier.choices)
    redeemed_at = models.DateTimeField(auto_now_add=True)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = (('promo_code', 'user'),)
        verbose_name = 'Uplatnění promo kódu'
        verbose_name_plural = 'Uplatnění promo kódů'

    def __str__(self):
        return f"{self.promo_code.code} → {self.user.username}"
