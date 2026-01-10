#!/bin/bash
# Debug script to check Celery status and errors

echo "=== Celery Debug Information ==="
echo ""

echo "1. Checking if Celery process is running:"
ps aux | grep -E "[c]elery.*worker" || echo "   ❌ Celery worker NOT running"
echo ""

echo "2. Checking Celery log file:"
if [ -f /tmp/celery.log ]; then
    echo "   ✅ Log file exists"
    echo "   Last 30 lines:"
    tail -30 /tmp/celery.log
else
    echo "   ❌ Log file not found at /tmp/celery.log"
fi
echo ""

echo "3. Testing Celery import:"
python -c "
try:
    from diet_planner.tasks import process_dietary_goal_task
    print('   ✅ Tasks module imports successfully')
except Exception as e:
    print(f'   ❌ Import error: {e}')
    import traceback
    traceback.print_exc()
"
echo ""

echo "4. Testing OpenAI service import:"
python -c "
try:
    from diet_planner.llm_service import OpenAIService
    print('   ✅ LLM service imports successfully')
    try:
        service = OpenAIService()
        print('   ✅ OpenAIService initialized successfully')
    except ValueError as e:
        print(f'   ⚠️  OpenAIService init error (expected if API key not set): {e}')
    except Exception as e:
        print(f'   ❌ OpenAIService init error: {e}')
except Exception as e:
    print(f'   ❌ Import error: {e}')
    import traceback
    traceback.print_exc()
"
echo ""

echo "5. Testing Redis connection:"
python -c "
try:
    import redis
    r = redis.Redis(host='127.0.0.1', port=6379, socket_connect_timeout=2)
    if r.ping():
        print('   ✅ Redis is reachable')
    else:
        print('   ❌ Redis ping failed')
except Exception as e:
    print(f'   ❌ Redis connection error: {e}')
"
echo ""

echo "6. Testing Celery configuration:"
python -c "
try:
    from celery import current_app
    print(f'   ✅ Celery app loaded')
    print(f'   Broker URL: {current_app.conf.broker_url}')
    print(f'   Result Backend: {current_app.conf.result_backend}')
except Exception as e:
    print(f'   ❌ Celery config error: {e}')
    import traceback
    traceback.print_exc()
"
echo ""

echo "7. Checking environment variables:"
echo "   OPENAI_API_KEY: $(if [ -n \"\$OPENAI_API_KEY\" ]; then echo 'SET'; else echo 'NOT SET'; fi)"
echo "   CELERY_BROKER_URL: ${CELERY_BROKER_URL:-NOT SET}"
echo "   CELERY_RESULT_BACKEND: ${CELERY_RESULT_BACKEND:-NOT SET}"
echo ""

echo "8. Attempting to start Celery manually (will show errors):"
timeout 5 celery -A llm_diet_planner_project worker --loglevel=info 2>&1 | head -20 || echo "   (Timeout or error occurred)"





