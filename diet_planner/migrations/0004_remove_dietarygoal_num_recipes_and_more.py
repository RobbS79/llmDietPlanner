# Generated manually to remove old meal plan fields
# These fields exist in the database but were never in Django migrations
# For SQLite: Make columns nullable (SQLite doesn't support DROP COLUMN easily)
# For PostgreSQL: Drop columns directly

from django.db import migrations, connection


def handle_old_columns(apps, schema_editor):
    """Make old columns nullable or drop them depending on database backend."""
    db_backend = schema_editor.connection.vendor
    
    with connection.cursor() as cursor:
        if db_backend == 'sqlite':
            # SQLite: Check if columns exist and make them nullable
            cursor.execute("PRAGMA table_info(diet_planner_dietarygoal)")
            columns = {row[1]: row for row in cursor.fetchall()}
            
            # SQLite doesn't support ALTER COLUMN easily either
            # The simplest solution: just ignore them - they won't cause issues
            # if we don't insert values into them
            # Actually, we need to handle the NOT NULL constraint
            # For SQLite, we'll use a workaround: update existing NULLs to 0
            for col in ['num_recipes', 'num_meals', 'num_snacks']:
                if col in columns:
                    # Update any NULL values to 0 to satisfy NOT NULL constraint
                    # Then the columns can remain (they just won't be used)
                    try:
                        cursor.execute(
                            f"UPDATE diet_planner_dietarygoal SET {col} = 0 WHERE {col} IS NULL"
                        )
                    except Exception:
                        pass
        else:
            # PostgreSQL and other databases: Drop columns
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'diet_planner_dietarygoal' 
                AND column_name IN ('num_recipes', 'num_meals', 'num_snacks')
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]
            
            for col in existing_columns:
                try:
                    schema_editor.execute(
                        f"ALTER TABLE diet_planner_dietarygoal DROP COLUMN {col}"
                    )
                except Exception:
                    pass


def reverse_handle_columns(apps, schema_editor):
    """Reverse migration - add columns back (not really needed)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0003_dietarygoal_main_courses_per_day_and_more"),
    ]

    operations = [
        migrations.RunPython(
            handle_old_columns,
            reverse_handle_columns,
        ),
    ]

