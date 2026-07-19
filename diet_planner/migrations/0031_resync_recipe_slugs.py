# Data migration: recompute Recipe.slug from the current name. Rows whose
# name was rewritten after creation kept the original dish's slug (e.g.
# /recepty/50/ovesna-kase/ serving a peanut soup), which reads as a broken
# product on the public showcase. Routing is by pk, so old URLs still resolve.

from django.db import migrations
from django.utils.text import slugify


def resync_slugs(apps, schema_editor):
    Recipe = apps.get_model('diet_planner', 'Recipe')
    for recipe in Recipe.objects.exclude(name='').only('id', 'name', 'slug'):
        fresh = slugify(recipe.name)[:255]
        if fresh and fresh != recipe.slug:
            Recipe.objects.filter(pk=recipe.pk).update(slug=fresh)


class Migration(migrations.Migration):

    dependencies = [
        ('diet_planner', '0030_update_site_name_varto'),
    ]

    operations = [
        migrations.RunPython(resync_slugs, migrations.RunPython.noop),
    ]
