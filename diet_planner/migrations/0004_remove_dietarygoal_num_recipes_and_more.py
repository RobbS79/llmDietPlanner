# Generated manually to remove old meal plan fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0003_dietarygoal_main_courses_per_day_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="dietarygoal",
            name="num_recipes",
        ),
        migrations.RemoveField(
            model_name="dietarygoal",
            name="num_meals",
        ),
        migrations.RemoveField(
            model_name="dietarygoal",
            name="num_snacks",
        ),
    ]

