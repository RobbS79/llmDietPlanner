"""
Update the default django.contrib.sites Site row's name to the new brand
"Uvařto" (was "Vařto" from migration 0030). The domain is unchanged here.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.filter(id=1).update(name="Uvařto")


def backwards(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.filter(id=1).update(name="Vařto")


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0042_nutrition_source_length"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
