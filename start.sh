#!/bin/bash
set -e

echo "=== DIETPLANNER PRODUCTION STARTUP ==="

# 1. Run migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# 2. Collect Statics
# This will ensure Whitenoise serves the React 'dist' assets correctly
echo "Collecting static files..."
python manage.py collectstatic --noinput

# 3. Start Infrastructure
echo "Starting Redis..."
redis-server --daemonize yes

echo "Starting Celery Worker..."
celery -A llm_diet_planner_project worker --loglevel=info &

# 4. Start Web Server
echo "Starting Gunicorn on port 8000..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application