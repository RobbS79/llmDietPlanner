#!/bin/bash
set -e

echo "=== Starting application ==="

echo "Creating migrations for diet_planner app..."
python manage.py makemigrations diet_planner --noinput || echo "Note: makemigrations may have failed or no changes needed"

echo "Running database migrations..."
python manage.py migrate --noinput || echo "Migration failed, continuing..."

echo "Collecting static files..."
python manage.py collectstatic --noinput || echo "Collectstatic failed, continuing..."

# Start Redis server in background (for in-container Celery)
echo "Starting Redis server..."
redis-server --daemonize yes --port 6379 --bind 127.0.0.1 || echo "Redis already running or failed to start"
sleep 2  # Give Redis time to start

# Verify Redis is running
if redis-cli -p 6379 ping > /dev/null 2>&1; then
    echo "Redis is running successfully"
else
    echo "Warning: Redis failed to start or is not accessible"
fi

# Start Celery worker in background using nohup (better for Docker than --detach)
echo "Starting Celery worker..."
nohup celery -A llm_diet_planner_project worker --loglevel=info > /tmp/celery.log 2>&1 &
CELERY_PID=$!
echo "Celery worker started with PID: $CELERY_PID"
sleep 2  # Give Celery time to start

# Verify Celery is running
if ps -p $CELERY_PID > /dev/null 2>&1; then
    echo "Celery worker is running (PID: $CELERY_PID)"
else
    echo "Warning: Celery worker may have failed to start (will use sync fallback)"
fi

# Start Gunicorn in foreground (main process - container stays alive)
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application

