from django.db import migrations, models
from django.utils.text import slugify


def backfill_slugs_and_public(apps, schema_editor):
    Recipe = apps.get_model('diet_planner', 'Recipe')
    for recipe in Recipe.objects.all():
        recipe.slug = slugify(recipe.name)[:255] if recipe.name else ''
        recipe.is_public = bool(recipe.instructions and len(recipe.instructions) > 0)
        recipe.save(update_fields=['slug', 'is_public'])


class Migration(migrations.Migration):

    dependencies = [
        ('diet_planner', '0012_add_historic_nutrition_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='recipe',
            name='slug',
            field=models.SlugField(blank=True, db_index=True, help_text='URL-friendly name', max_length=255),
        ),
        migrations.AddField(
            model_name='recipe',
            name='is_public',
            field=models.BooleanField(db_index=True, default=False, help_text='Visible on public recipe pages'),
        ),
        migrations.AddIndex(
            model_name='recipe',
            index=models.Index(fields=['is_public', '-created_at'], name='diet_plann_recipe_public_idx'),
        ),
        migrations.RunPython(backfill_slugs_and_public, migrations.RunPython.noop),
    ]
