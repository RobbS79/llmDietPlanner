from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diet_planner', '0013_recipe_slug_is_public'),
    ]

    operations = [
        migrations.AddField(
            model_name='recipe',
            name='food_category',
            field=models.CharField(blank=True, db_index=True, default='', help_text='Food category slug for stock image mapping', max_length=50),
        ),
    ]
