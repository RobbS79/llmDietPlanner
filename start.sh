#!/bin/bash
set -e

echo "=== DIETPLANNER PRODUCTION STARTUP ==="

# 1. Database Migrations
python manage.py migrate --noinput

# 2. Collect Static Files
# This creates the /app/staticfiles directory you mentioned was missing
echo "Creating staticfiles directory and collecting assets..."
python manage.py collectstatic --noinput --clear

# 3. Start Infrastructure (Background)
redis-server --daemonize yes
# Start Celery with limited concurrency to save memory on basic-xxs
celery -A llm_diet_planner_project worker --concurrency=2 --loglevel=info &

# 4. Start Gunicorn
# Reduced workers from 3 to 2 to prevent OOM (Out of Memory) kills
echo "Starting Gunicorn with 2 workers..."
exec gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 llm_diet_planner_project.wsgi:application