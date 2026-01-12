#!/bin/bash
set -e

echo "=== Starting application ==="

# Force collection of static files to ensure CSS updates are picked up
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Running migrations..."
python manage.py migrate --noinput

# Infrastructure
echo "Starting Redis..."
redis-server --daemonize yes
sleep 1

echo "Starting Celery..."
nohup celery -A llm_diet_planner_project worker --loglevel=info > /tmp/celery.log 2>&1 &

echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application