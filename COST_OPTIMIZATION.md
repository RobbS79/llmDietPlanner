# Cost-Optimized Celery Setup (Single Container)

## Overview

This approach runs **Redis + Celery worker + Gunicorn** all in a **single Docker container**, eliminating:
- ❌ Separate Redis database cost (~$15/month)
- ❌ Separate Celery worker service cost (~$5-12/month)

**Total Savings: ~$20-27/month**

## How It Works

1. **Redis runs inside the container** (in-memory, port 6379)
2. **Celery worker runs as background process** in the same container
3. **Gunicorn runs as main process** (foreground)

All processes share the same container resources.

## Trade-offs

### ✅ Advantages
- **Much cheaper** (~$20-27/month savings)
- **Simpler setup** (no separate services to configure)
- **Good for MVP/early stage** when cost matters
- **Redis in-memory is fine** for Celery tasks (they're transient, not meant to persist)

### ⚠️ Limitations
- **Less isolation** - processes share resources
- **Single point of failure** - if container crashes, everything goes down
- **Redis data lost on restart** - but that's OK for task queue (tasks are meant to be processed)
- **Resource contention** - Gunicorn + Celery + Redis share CPU/memory
- **Not ideal for high scale** - but fine for 100k users if you scale the container size

## Setup Instructions

### Option 1: Update Existing Files (Recommended for Cost Savings)

1. **Update Dockerfile.prod** to install Redis:
```dockerfile
# Add redis-server to apt-get install
RUN apt-get update && apt-get install -y \
    postgresql-client \
    redis-server \
    && rm -rf /var/lib/apt/lists/*
```

2. **Update start.sh** to run Redis and Celery:
```bash
# Start Redis in background
redis-server --daemonize yes --port 6379 --bind 127.0.0.1

# Start Celery worker in background  
celery -A llm_diet_planner_project worker --loglevel=info --detach

# Start Gunicorn in foreground
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 llm_diet_planner_project.wsgi:application
```

3. **Update .do/app.yaml** - Remove separate Celery service and Redis database:
```yaml
services:
  - name: web
    # ... existing config ...
    envs:
      # ... existing envs ...
      - key: CELERY_BROKER_URL
        value: "redis://127.0.0.1:6379/0"
      - key: CELERY_RESULT_BACKEND
        value: "redis://127.0.0.1:6379/0"
    # Remove celery service
    # Remove databases section
```

### Option 2: Use Provided Files

I've created:
- `Dockerfile.prod.cheap` - Dockerfile with Redis installed
- `start.sh.with-redis-celery` - Startup script with Redis + Celery

Copy these over your existing files if you want to use them.

## Environment Variables

In DigitalOcean App Platform, set:
- `CELERY_BROKER_URL=redis://127.0.0.1:6379/0`
- `CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0`

No external Redis database needed!

## When to Upgrade to Separate Services

Consider separate services when:
- **High traffic** - Need independent scaling
- **High availability required** - Need redundancy
- **Complex workloads** - Need resource isolation
- **Budget allows** - Can afford ~$20-27/month more

For MVP/early stage, single container is perfectly fine!

## Verification

After deployment:
1. Check logs - should see Redis starting, Celery worker starting, then Gunicorn
2. Register a user - should work with async email
3. Check Celery logs - tasks should be processed

## Alternative: Even Simpler (No Redis)

If you want to eliminate Redis entirely for now, you could:
- Use Django's database as Celery broker (slower but simpler)
- Or just use synchronous email (current fallback)

But Redis in-container is the sweet spot - cheap and still async!

