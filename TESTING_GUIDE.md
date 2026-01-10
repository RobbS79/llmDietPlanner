# Testing OpenAI Integration - Quick Start Guide

## Prerequisites

Before testing at `http://localhost:8000/`, ensure you have:

1. **OpenAI API Key** - Get one from https://platform.openai.com/api-keys
2. **Python dependencies installed**
3. **Database migrations run**
4. **Redis running** (for Celery async tasks)
5. **Celery worker running** (for background processing)

## Step-by-Step Setup

### 1. Install Dependencies

```bash
# Activate your virtual environment (if using one)
source venv/bin/activate  # or: python -m venv venv && source venv/bin/activate

# Install new dependencies
pip install -r requirements.txt
```

This will install:
- `openai>=1.12.0`
- `tiktoken>=0.5.0`

### 2. Set Environment Variables

Create a `.env` file in the project root (or export them):

```bash
# .env file
OPENAI_API_KEY=sk-your-actual-api-key-here
OPENAI_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3  # or your PostgreSQL URL
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

**Or export directly:**
```bash
export OPENAI_API_KEY="sk-your-actual-api-key-here"
export OPENAI_MODEL="gpt-4o-mini"
```

### 3. Run Database Migrations

```bash
# Create migrations for new model fields
python manage.py makemigrations diet_planner

# Apply migrations
python manage.py migrate
```

This adds the new fields:
- `llm_input_tokens`
- `llm_output_tokens`
- `llm_total_tokens`
- `llm_cost_usd`
- `llm_model_used`

### 4. Start Redis (Required for Celery)

**Option A: Using Docker (Recommended)**
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

**Option B: Install locally**
```bash
# macOS
brew install redis
brew services start redis

# Linux
sudo apt-get install redis-server
sudo systemctl start redis
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

### 5. Start Celery Worker (Terminal 1)

```bash
celery -A llm_diet_planner_project worker --loglevel=info
```

Keep this terminal open - you'll see task logs here.

### 6. Start Django Server (Terminal 2)

```bash
python manage.py runserver
```

Server will start at `http://localhost:8000/`

## Testing the Integration

### Option 1: Using the Frontend

1. Navigate to `http://localhost:8000/`
2. Log in or register
3. Create a new dietary goal
4. Watch the status change from `pending` → `processing` → `completed`
5. View the generated plan with meal ideas and shopping list
6. Check the `llm_usage` field for token counts and cost

### Option 2: Using API Directly

**1. Create a Dietary Goal:**
```bash
curl -X POST http://localhost:8000/api/diet-planner/goals/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "prompt": "I want to lose 5kg in 2 months",
    "dietary_restrictions": "No gluten",
    "country": "PL",
    "city": "Warsaw",
    "language_code": "pl"
  }'
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "goal_id": 1,
    "status": "pending",
    "task_id": "abc-123-def",
    "message": "Dietary goal created. Processing will begin shortly."
  }
}
```

**2. Poll for Task Status:**
```bash
curl http://localhost:8000/api/diet-planner/goals/1/task-status/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**3. Get Completed Plan:**
```bash
curl http://localhost:8000/api/diet-planner/goals/1/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response includes:**
```json
{
  "status": "success",
  "data": {
    "id": 1,
    "status": "completed",
    "dietary_plan": {
      "meal_ideas": [...],
      "shopping_list": [...],
      "llm_usage": {
        "input_tokens": 1234,
        "output_tokens": 567,
        "total_tokens": 1801,
        "cost_usd": "0.002345",
        "model": "gpt-4o-mini"
      }
    }
  }
}
```

## Troubleshooting

### "OPENAI_API_KEY not set"
- Make sure `.env` file exists or environment variable is exported
- Check `python manage.py shell` → `from django.conf import settings; print(settings.OPENAI_API_KEY)`

### "Celery task could not be triggered"
- Ensure Redis is running: `redis-cli ping`
- Ensure Celery worker is running: Check terminal with `celery -A llm_diet_planner_project worker`

### "No module named 'openai'"
- Run: `pip install -r requirements.txt`

### Task stays in "pending" status
- Check Celery worker logs for errors
- Verify Redis connection: `CELERY_BROKER_URL` in settings

### Migration errors
- Run: `python manage.py makemigrations diet_planner`
- Then: `python manage.py migrate`

## Quick Test Commands

```bash
# Check if OpenAI is configured
python manage.py shell -c "from django.conf import settings; print('OpenAI Key:', 'SET' if settings.OPENAI_API_KEY else 'NOT SET')"

# Check Celery connection
python manage.py shell -c "from celery import current_app; print('Broker:', current_app.conf.broker_url)"

# Test OpenAI connection (uses API key)
python manage.py shell -c "from diet_planner.llm_service import OpenAIService; s = OpenAIService(); print('OpenAI Service OK')"
```

## Expected Behavior

1. **Create Goal** → Returns immediately with `task_id`
2. **Task Processing** → Takes 10-30 seconds (LLM generation)
3. **Status Updates** → `pending` → `processing` → `completed`
4. **Cost Tracking** → Stored in database and returned in API
5. **Plan Available** → Meal ideas and shopping list ready

## Cost Notes

- `gpt-4o-mini`: ~$0.15 per 1M input tokens, $0.60 per 1M output tokens
- Typical request: ~1,000-2,000 tokens total
- Cost per request: ~$0.0002 - $0.001 (very cheap!)

Happy testing! 🚀





