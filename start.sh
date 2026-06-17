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
  # Idempotent upsert: create the superuser if absent, otherwise RESET its
  # password. `createsuperuser --noinput` only *creates* — it no-ops when the
  # user already exists, so it cannot recover a lost prod admin password (the
  # real lockout mode). Resetting from the secret on every boot keeps /admin/
  # reachable with a known credential.
  DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-admin}" \
  DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-soroka.robert8@gmail.com}" \
  python manage.py shell <<'PYEOF'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]

user, created = User.objects.get_or_create(username=username, defaults={"email": email})
user.is_staff = True
user.is_superuser = True
if email and not user.email:
    user.email = email
user.set_password(password)
user.save()
print("Superuser created." if created else "Superuser password reset.")
PYEOF
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