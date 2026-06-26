"""
Update the default django.contrib.sites Site row's name to the new brand
"Vařto" (was "DietPlanner AI" from migration 0024). Domain stays eatalnicek.eu.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.filter(id=1).update(name="Vařto")


def backwards(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.filter(id=1).update(name="DietPlanner AI")


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0029_remove_dietaryplan_pantry_basics_on_and_more"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
