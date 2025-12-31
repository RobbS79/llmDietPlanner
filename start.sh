#!/bin/bash
set -e

echo "=== Starting application ==="

echo "Creating migrations for diet_planner app..."
python manage.py makemigrations diet_planner --noinput || echo "Note: makemigrations may have failed or no changes needed"

echo "Running database migrations..."
python manage.py migrate --noinput || echo "Migration failed, continuing..."

echo "Collecting static files..."
python manage.py collectstatic --noinput || echo "Collectstatic failed, continuing..."

echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application

