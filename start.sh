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

# 3. Static Asset Aggregation (needed before serving).
# Kept on the critical path, but --clear dropped: a fresh container's
# staticfiles/ is already empty, so the extra delete pass only slowed startup.
echo "Collecting UI Assets..."
python manage.py collectstatic --noinput

# 4. Deferred bootstrap — idempotent, NON-serving setup.
# WHY DEFERRED: the canonical-dictionary seed, superuser upsert, QA account, and
# admin TOTP enrollment each cold-boot Django (~seconds) and NONE is required to
# serve traffic or to answer the platform's TCP readiness probe on :8000.
# Running them inline (as before) meant Gunicorn only bound the port after ~5
# sequential manage.py commands, so a slow cold start lost the race with the
# default health-check window and the whole deploy was rolled back. We now run
# them in the background after a short delay: Gunicorn binds promptly (right
# after migrate + collectstatic), the probe passes, and this work lands a few
# seconds into serving without contending for memory during the probe window.
# Every step stays idempotent and non-fatal (a failure only WARNs; the next
# deploy re-runs it).
echo "Scheduling deferred bootstrap (dictionary, superuser, QA, TOTP)..."
(
  # Let Gunicorn bind and pass the readiness probe before we spend memory here.
  sleep 20

  # 4a. Canonical ingredient dictionary (recipe→catalog mapping / real pricing).
  # Lives in data/canonical_ingredients.yaml, not a migration, so a schema-only
  # deploy would miss dictionary growth. Idempotent (upsert by slug).
  echo "[deferred] Seeding canonical ingredient dictionary..."
  python manage.py seed_canonical_ingredients || echo "WARN: canonical ingredient seed failed (dictionary may be stale)."

  # 4b. Superuser upsert.
  # SECURITY (incident 2026-06-02-dbminer): the password must NEVER be hard-coded
  # here — this file is committed to git. Source it from the DO SECRET env var
  # DJANGO_SUPERUSER_PASSWORD; if absent, skip rather than use a default.
  # Idempotent: create if absent, otherwise RESET the password from the secret
  # so /admin/ stays reachable with a known credential (createsuperuser --noinput
  # only creates and cannot recover a lost password).
  if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "[deferred] Ensuring superuser..."
    DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-admin}" \
    DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-soroka.robert8@gmail.com}" \
    python manage.py shell <<'PYEOF' || echo "WARN: superuser bootstrap failed."
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
    echo "[deferred] DJANGO_SUPERUSER_PASSWORD not set — skipping superuser bootstrap."
  fi

  # 4c. QA verification account (post-deploy /qa-prod). Credentials come only
  # from DO SECRET env vars; the command no-ops when they are absent. Idempotent.
  echo "[deferred] Seeding QA account..."
  python manage.py seed_qa_account || echo "WARN: QA account seed failed."

  # 4d. Admin TOTP MFA device (console-free enrollment). OTPAdminSite locks
  # /admin/ until a confirmed TOTP device exists; the operator supplies the
  # secret as a DO SECRET env var and we seed the device on every boot.
  # Idempotent (--secret derives a fixed key). --quiet keeps it out of logs.
  if [ -n "$ADMIN_TOTP_SECRET" ]; then
    echo "[deferred] Enrolling admin TOTP device from ADMIN_TOTP_SECRET..."
    python manage.py setup_admin_totp "${DJANGO_SUPERUSER_USERNAME:-admin}" \
      --secret "$ADMIN_TOTP_SECRET" --quiet || echo "WARN: admin TOTP enrollment failed (admin may be locked)."
  else
    echo "[deferred] ADMIN_TOTP_SECRET not set — admin MFA device not bootstrapped."
  fi
) &

# 5. Launch Synthesis Worker
# Concurrency limited to 1 to optimize memory footprint on basic instances
echo "Starting Synthesis Worker (Celery)..."
celery -A llm_diet_planner_project worker --concurrency=1 --loglevel=info &

# 6. Launch Beat Scheduler (proactive scraping + freshness lifecycle)
# Disabled on basic-xxs to save ~100MB RAM for the worker
# Re-enable when upgrading to basic-xs or larger
# echo "Starting Beat Scheduler..."
# celery -A llm_diet_planner_project beat --loglevel=info &

# 7. Launch Application Server
# exec so Gunicorn is PID 1 and receives SIGTERM directly for graceful drain.
echo "Starting Application Hub (Gunicorn)..."
exec gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 llm_diet_planner_project.wsgi:application
