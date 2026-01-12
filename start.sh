#!/bin/bash
set -e

echo "=== Starting application ==="

# 1. Verification of frontend build
if [ ! -d "/app/frontend/build" ]; then
    echo "ERROR: /app/frontend/build does not exist. CSS/JS colors will be broken."
else
    echo "Frontend build folder found."
fi

# 2. Database Migrations
echo "Creating migrations for diet_planner app..."
python manage.py makemigrations diet_planner --noinput || echo "makemigrations failed, continuing..."

echo "Running database migrations..."
python manage.py migrate --noinput

# 3. Static Files (Crucial for dark blue styles)
echo "Collecting static files..."
# We run this to move React build assets into the static_root for WhiteNoise
python manage.py collectstatic --noinput --clear

# 4. Infrastructure (Redis/Celery)
echo "Starting Redis server..."
redis-server --daemonize yes --port 6379 --bind 127.0.0.1
sleep 2

echo "Starting Celery worker..."
nohup celery -A llm_diet_planner_project worker --loglevel=info > /tmp/celery.log 2>&1 &
CELERY_PID=$!
echo "Celery worker started with PID: $CELERY_PID"

# 5. Launch Backend
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application