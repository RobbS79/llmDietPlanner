"""
Rebrand the seeded subscription tiers from "Vařto" to "Uvařto".

Names are data, so this is a data migration; the AlterField only carries the
updated help_text example.
"""
from django.db import migrations, models


RENAMES = {
    'standard': ('Vařto Standard', 'Uvařto Standard'),
    'premium': ('Vařto Premium', 'Uvařto Premium'),
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
        ('billing', '0006_promocode_percent_check'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscriptionplan',
            name='name',
            field=models.CharField(
                help_text="Display name, e.g. 'Uvařto Standard'.", max_length=100),
        ),
        migrations.RunPython(rename_forward, rename_backward),
    ]
