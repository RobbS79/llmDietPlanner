"""
Rebrand the seeded subscription tiers from "Eatalníček" to "Vařto".

The public site was renamed Vařto on 2026-06-25, but the two SubscriptionPlan
rows seeded by 0002 kept the old brand, so /api/billing/plans/ (and admin)
still said "Eatalníček Standard". Names are data, so this is a data migration.
"""
from django.db import migrations, models


RENAMES = {
    'standard': ('Eatalníček Standard', 'Vařto Standard'),
    'premium': ('Eatalníček Premium', 'Vařto Premium'),
}


def rename_forward(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    for tier, (_old, new) in RENAMES.items():
        SubscriptionPlan.objects.filter(tier=tier).update(name=new)


def rename_backward(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    for tier, (old, _new) in RENAMES.items():
        SubscriptionPlan.objects.filter(tier=tier).update(name=old)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_stripecustomer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscriptionplan',
            name='name',
            field=models.CharField(
                help_text="Display name, e.g. 'Vařto Standard'.", max_length=100),
        ),
        migrations.RunPython(rename_forward, rename_backward),
    ]
