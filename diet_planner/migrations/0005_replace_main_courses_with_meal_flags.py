# Generated manually to replace main_courses_per_day with breakfast/lunch/dinner booleans

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0004_remove_dietarygoal_num_recipes_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dietarygoal",
            name="breakfast",
            field=models.BooleanField(
                default=True,
                help_text="Include breakfast in the meal plan"
            ),
        ),
        migrations.AddField(
            model_name="dietarygoal",
            name="lunch",
            field=models.BooleanField(
                default=True,
                help_text="Include lunch in the meal plan"
            ),
        ),
        migrations.AddField(
            model_name="dietarygoal",
            name="dinner",
            field=models.BooleanField(
                default=True,
                help_text="Include dinner in the meal plan"
            ),
        ),
        migrations.RemoveField(
            model_name="dietarygoal",
            name="main_courses_per_day",
        ),
    ]




