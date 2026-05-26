from django.db import migrations


def backfill_food_category(apps, schema_editor):
    from diet_planner.food_categories import guess_category
    Recipe = apps.get_model('diet_planner', 'Recipe')
    for recipe in Recipe.objects.filter(food_category=''):
        recipe.food_category = guess_category(recipe.name, recipe.ingredients)
        recipe.save(update_fields=['food_category'])


class Migration(migrations.Migration):

    dependencies = [
        ('diet_planner', '0014_recipe_food_category'),
    ]

    operations = [
        migrations.RunPython(backfill_food_category, migrations.RunPython.noop),
    ]
