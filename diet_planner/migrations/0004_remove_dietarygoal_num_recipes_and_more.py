# Generated manually to remove old meal plan fields
# These fields exist in the database but were never in Django migrations
# Using RunSQL to drop them directly

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0003_dietarygoal_main_courses_per_day_and_more"),
    ]

    operations = [
        # Drop columns directly using SQL since they're not in Django's migration state
        migrations.RunSQL(
            sql=[
                "ALTER TABLE diet_planner_dietarygoal DROP COLUMN IF EXISTS num_recipes;",
                "ALTER TABLE diet_planner_dietarygoal DROP COLUMN IF EXISTS num_meals;",
                "ALTER TABLE diet_planner_dietarygoal DROP COLUMN IF EXISTS num_snacks;",
            ],
            reverse_sql=[
                # Reverse migration - add columns back if needed (with defaults)
                "ALTER TABLE diet_planner_dietarygoal ADD COLUMN IF NOT EXISTS num_recipes INTEGER DEFAULT 7;",
                "ALTER TABLE diet_planner_dietarygoal ADD COLUMN IF NOT EXISTS num_meals INTEGER DEFAULT 14;",
                "ALTER TABLE diet_planner_dietarygoal ADD COLUMN IF NOT EXISTS num_snacks INTEGER DEFAULT 7;",
            ],
        ),
    ]

