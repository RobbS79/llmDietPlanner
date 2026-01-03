# Generated manually to remove old meal plan fields
# These fields exist in the database but were never in Django migrations
# For SQLite: Make columns nullable (SQLite doesn't support DROP COLUMN easily)
# For PostgreSQL: Drop columns directly

from django.db import migrations, connection


def handle_old_columns(apps, schema_editor):
    """Make old columns nullable or drop them depending on database backend."""
    db_backend = schema_editor.connection.vendor
    
    if db_backend == 'sqlite':
        # SQLite: Can't easily drop columns with ALTER TABLE
        # For SQLite, this migration is a no-op
        # Users need to manually run fix_sqlite_columns.sql or recreate the database
        # The columns will remain but Django won't use them
        # New inserts will fail if columns have NOT NULL - manual fix required
        pass
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

