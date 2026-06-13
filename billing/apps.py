"""
App configuration for billing.

Houses Stripe Billing integration: SubscriptionPlan (tier config),
Subscription (user-level entitlement, system of record), and the
webhook-idempotency ledger. See docs/stripe-billing-plan.md.
"""
from django.apps import AppConfig


class BillingConfig(AppConfig):
    """Configuration for the billing app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'
    verbose_name = 'Billing & Subscriptions'
