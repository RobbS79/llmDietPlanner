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

# 2b. Ensure superuser exists
# SECURITY (incident 2026-06-02-dbminer): the superuser password must NEVER be
# hard-coded here — this file is committed to git, so any literal becomes a
# leaked production admin credential. Source it from a DO App Platform SECRET
# env var (DJANGO_SUPERUSER_PASSWORD). If the secret is absent we skip creation
# rather than fall back to a known/default password.
echo "Ensuring superuser..."
if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-admin}" \
  DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-soroka.robert8@gmail.com}" \
  python manage.py createsuperuser --noinput 2>/dev/null || echo "Superuser already exists"
else
  echo "DJANGO_SUPERUSER_PASSWORD not set — skipping superuser bootstrap."
fi

# 3. Static Asset Aggregation
echo "Collecting UI Assets..."
python manage.py collectstatic --noinput --clear

# 4. Launch Synthesis Worker
# Concurrency limited to 2 to optimize memory footprint on basic-xxs instances
echo "Starting Synthesis Worker (Celery)..."
celery -A llm_diet_planner_project worker --concurrency=1 --loglevel=info &

# 5. Launch Beat Scheduler (proactive scraping + freshness lifecycle)
# Disabled on basic-xxs to save ~100MB RAM for the worker
# Re-enable when upgrading to basic-xs or larger
# echo "Starting Beat Scheduler..."
# celery -A llm_diet_planner_project beat --loglevel=info &

# 6. Launch Application Server
echo "Starting Application Hub (Gunicorn)..."
exec gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 llm_diet_planner_project.wsgi:application