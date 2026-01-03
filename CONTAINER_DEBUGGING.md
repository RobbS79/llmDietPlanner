# Debugging Inside Digital Ocean Container

## You're Already Inside the Container!

When you see `root@llmdietplanner-...:/app#`, you're inside the running container.

## Check Logs Inside Container

### 1. Check Django/Gunicorn Logs
```bash
# Check if Gunicorn is running
ps aux | grep gunicorn

# Check recent Django logs (if logging to file)
tail -f /var/log/gunicorn/access.log
tail -f /var/log/gunicorn/error.log

# Or check stdout/stderr (usually captured by Digital Ocean)
```

### 2. Check Celery Worker Logs
```bash
# Check if Celery is running
ps aux | grep celery

# Check Celery logs (if logging to file)
tail -f /tmp/celery.log

# Or check process output
```

### 3. Check Application Status
```bash
# Check if Django can connect to database
python manage.py check --database default

# Check if OpenAI key is set
python manage.py shell -c "from django.conf import settings; print('OpenAI Key:', 'SET' if settings.OPENAI_API_KEY else 'NOT SET')"

# Check Redis connection
python manage.py shell -c "from celery import current_app; print('Broker:', current_app.conf.broker_url)"
```

### 4. Check Environment Variables
```bash
# List all environment variables
env | grep -E "(OPENAI|CELERY|DATABASE|SECRET)"

# Check specific variable
echo $OPENAI_API_KEY
echo $CELERY_BROKER_URL
```

### 5. Check Running Processes
```bash
# See all running processes
ps aux

# Check specific services
ps aux | grep -E "(gunicorn|celery|redis|python)"
```

### 6. Test OpenAI Connection
```bash
# Test OpenAI service
python manage.py shell
>>> from diet_planner.llm_service import OpenAIService
>>> service = OpenAIService()
>>> print("OpenAI service initialized successfully")
```

### 7. Check Database Migrations
```bash
# Check migration status
python manage.py showmigrations diet_planner

# Run migrations manually if needed
python manage.py migrate
```

### 8. Check Redis Connection
```bash
# If redis-cli is available
redis-cli -h 127.0.0.1 -p 6379 ping

# Or test via Python
python manage.py shell -c "import redis; r = redis.Redis(host='127.0.0.1', port=6379); print('Redis:', r.ping())"
```

## Common Issues & Solutions

### Issue: OPENAI_API_KEY not set
```bash
# Check if it's in environment
echo $OPENAI_API_KEY

# If empty, it needs to be set in Digital Ocean dashboard
# Settings → App-Level Environment Variables → Add OPENAI_API_KEY as SECRET
```

### Issue: Celery not processing tasks
```bash
# Check if Celery worker is running
ps aux | grep celery

# Check Celery logs
tail -f /tmp/celery.log

# Restart Celery (if you have permissions)
pkill -f celery
celery -A llm_diet_planner_project worker --loglevel=info &
```

### Issue: Database connection errors
```bash
# Test database connection
python manage.py dbshell

# Check DATABASE_URL
echo $DATABASE_URL
```

## View Logs from Digital Ocean Dashboard

**Better approach:** Exit the container and use the Digital Ocean web UI:

1. Exit the container: `exit`
2. Go to https://cloud.digitalocean.com/apps
3. Click your app → "Runtime Logs" tab
4. This shows all logs in real-time

## Quick Health Check Script

Run this inside the container:

```bash
echo "=== Environment Check ==="
echo "OpenAI Key: $(python -c "from django.conf import settings; print('SET' if settings.OPENAI_API_KEY else 'NOT SET')")"
echo "Celery Running: $(ps aux | grep -q '[c]elery' && echo 'YES' || echo 'NO')"
echo "Gunicorn Running: $(ps aux | grep -q '[g]unicorn' && echo 'YES' || echo 'NO')"
echo "Redis Reachable: $(python -c "import redis; r = redis.Redis(host='127.0.0.1', port=6379); print('YES' if r.ping() else 'NO')" 2>/dev/null || echo 'NO')"
```


