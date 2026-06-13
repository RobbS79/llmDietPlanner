"""
Seed the two subscription tiers.

Quotas/prices taken verbatim from frontend/src/pages/Pricing.tsx PLANS:
  Standard — 99 CZK/mo, 7 plans, 10 edits/plan, single-store
  Premium  — 199 CZK/mo, 30 plans, 5 edits/plan, multi-store

stripe_price_id is intentionally left blank: the live/test Price IDs are
supplied per-environment via STRIPE_PRICE_STANDARD / STRIPE_PRICE_PREMIUM
(settings/env). Set the field here only if you prefer DB-driven price IDs.
"""
from django.db import migrations


PLANS = [
    {
        'tier': 'standard',
        'name': 'Eatalníček Standard',
        'price_czk': 99,
        'monthly_plan_quota': 7,
        'edits_per_plan': 10,
        'allow_multi_store': False,
        'sort_order': 1,
    },
    {
        'tier': 'premium',
        'name': 'Eatalníček Premium',
        'price_czk': 199,
        'monthly_plan_quota': 30,
        'edits_per_plan': 5,
        'allow_multi_store': True,
        'sort_order': 2,
    },
]


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    for plan in PLANS:
        SubscriptionPlan.objects.update_or_create(
            tier=plan['tier'], defaults=plan,
        )


def unseed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(
        tier__in=[p['tier'] for p in PLANS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_plans, unseed_plans),
    ]
