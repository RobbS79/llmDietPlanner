#!/bin/bash
set -e

echo "=== DIETPLANNER STARTUP SEQUENCE ==="

# 1. Database Migrations
echo "Checking and applying database migrations..."
python manage.py migrate --noinput

# 2. Collect Static Files (CRITICAL FIX)
# This finds the React 'dist' folder and moves it to 'staticfiles'
echo "Collecting static files (React artifacts)..."
python manage.py collectstatic --noinput --clear

# 3. Start Background Services
echo "Starting Redis..."
redis-server --daemonize yes

echo "Starting Celery..."
celery -A llm_diet_planner_project worker --loglevel=info &

# 4. Launch Application
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application