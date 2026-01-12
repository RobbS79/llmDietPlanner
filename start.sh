#!/bin/bash
set -e

echo "=== Starting application ==="

# 1. Run migrations only (skip makemigrations in prod)
python manage.py migrate --noinput

# 2. Start services in the background
redis-server --daemonize yes
celery -A llm_diet_planner_project worker --loglevel=info &

# 3. Start Gunicorn immediately
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application