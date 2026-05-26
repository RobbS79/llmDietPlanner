#!/bin/bash
# File: start.sh
# Purpose: Production entrypoint for Digital Ocean App Platform.
# Note: Ensure this file is saved with LF line endings.

set -e

echo "=== DIETPLANNER PRODUCTION STARTUP ==="

# 1. Start Infrastructure Dependencies
# Start local Redis for the 'cheap' deployment model
redis-server --daemonize yes

# Wait for Redis to become responsive (Critical for Celery handshake)
echo "Verifying Hub Connectivity (Redis)..."
RETRIES=10
until redis-cli ping | grep -q PONG || [ $RETRIES -eq 0 ]; do
  echo "Hub offline - retrying... ($RETRIES left)"
  sleep 2
  RETRIES=$((RETRIES-1))
done

if [ $RETRIES -eq 0 ]; then
  echo "FATAL: Could not establish connectivity with Redis Hub."
  exit 1
fi

# 2. Database Synchronization
echo "Synchronizing Schema..."
python manage.py migrate --noinput

# 3. Static Asset Aggregation
echo "Collecting UI Assets..."
python manage.py collectstatic --noinput --clear

# 4. Launch Synthesis Worker
# Concurrency limited to 2 to optimize memory footprint on basic-xxs instances
echo "Starting Synthesis Worker (Celery)..."
celery -A llm_diet_planner_project worker --concurrency=2 --loglevel=info &

# 5. Launch Beat Scheduler (proactive scraping + freshness lifecycle)
echo "Starting Beat Scheduler..."
celery -A llm_diet_planner_project beat --loglevel=info &

# 6. Launch Application Server
echo "Starting Application Hub (Gunicorn)..."
exec gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 llm_diet_planner_project.wsgi:application