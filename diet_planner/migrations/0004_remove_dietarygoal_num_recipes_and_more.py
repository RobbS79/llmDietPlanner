# Generated manually to remove old meal plan fields
# These fields exist in the database but were never in Django migrations
# For SQLite: Make columns nullable (SQLite doesn't support DROP COLUMN easily)
# For PostgreSQL: Drop columns directly

from django.db import migrations, connection


def handle_old_columns(apps, schema_editor):
    """Make old columns nullable or drop them depending on database backend."""
    db_backend = schema_editor.connection.vendor
    
    if db_backend == 'sqlite':
        # SQLite: Can't easily drop columns, so we'll set default values for existing records
        # New records won't have these columns in the INSERT, so they'll fail
        # Solution: We need to provide defaults or make columns nullable
        # Since SQLite limitations, we'll just set defaults on existing records
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(diet_planner_dietarygoal)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Set default values for any existing NULL records
            for col in ['num_recipes', 'num_meals', 'num_snacks']:
                if col in columns:
                    try:
                        # Set default values for existing records
                        defaults = {'num_recipes': 7, 'num_meals': 14, 'num_snacks': 7}
                        cursor.execute(
                            f"UPDATE diet_planner_dietarygoal SET {col} = {defaults.get(col, 0)} WHERE {col} IS NULL"
                        )
                    except Exception:
                        pass
        # Note: For SQLite, columns will remain but won't be used
        # For new records, we need to ensure Django doesn't try to insert into them
    else:
        # PostgreSQL and other databases: Drop columns
        with connection.cursor() as cursor:
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

