# Celery Async Email Setup for DigitalOcean App Platform

## Overview

Email sending is configured to be **async via Celery** for better performance and reliability. This requires:

1. **Redis database** (for Celery message broker)
2. **Celery worker service** (to process async tasks)

## DigitalOcean App Platform Configuration

### Step 1: Add Redis Database

1. Go to your app in DigitalOcean App Platform
2. Navigate to **Components** or **Resources**
3. Click **Add Resource** → **Database**
4. Select **Redis**
5. Choose version **7**
6. Note the connection URL (you'll need this for environment variables)

### Step 2: Configure Environment Variables

Add these environment variables to both `web` and `celery` services:

#### For Redis Connection (from the database you just created):
- **Key**: `CELERY_BROKER_URL`
- **Value**: The Redis connection URL from DigitalOcean (format: `redis://...`)
- **Scope**: `RUN_TIME`
- **Type**: `SECRET`

- **Key**: `CELERY_RESULT_BACKEND`  
- **Value**: Same Redis connection URL
- **Scope**: `RUN_TIME`
- **Type**: `SECRET`

### Step 3: Add Celery Worker Service

The `.do/app.yaml` file already includes a `celery` service. If you're configuring via UI:

1. Go to **Components** → **Add Component** → **Worker**
2. Configure:
   - **Name**: `celery`
   - **Dockerfile**: `Dockerfile.prod`
   - **Run Command**: `celery -A llm_diet_planner_project worker --loglevel=info`
   - **Environment Variables**: Same as `web` service (SECRET_KEY, DATABASE_URL, CELERY_BROKER_URL, etc.)

### Step 4: Update app.yaml (if using file-based config)

The `.do/app.yaml` file has been updated with:
- Redis database component
- Celery worker service
- Required environment variables

Make sure to:
- Update `YOUR_GITHUB_USERNAME` with your actual GitHub username
- Update `your-app-name.ondigitalocean.app` with your actual app domain

## How It Works

1. **User registers** → RegistrationView creates user
2. **Email task queued** → `send_verification_email_task.delay()` queues task to Redis
3. **Celery worker picks up task** → Worker processes email sending asynchronously
4. **Email sent** → User receives verification email

## Benefits of Async Email

- ✅ **Non-blocking**: Registration completes immediately, user doesn't wait for email
- ✅ **Reliable**: Celery retries failed emails automatically (up to 3 times)
- ✅ **Scalable**: Can handle many registrations without blocking
- ✅ **Better UX**: Fast response times

## Fallback Behavior

If Celery is not available (Redis not configured or worker not running), the system automatically falls back to **synchronous email sending**. This ensures emails are still sent, but registration will be slightly slower.

## Cost Considerations

- **Redis Database**: ~$15/month (smallest plan)
- **Celery Worker Service**: Same cost as web service (based on instance size)

**Total additional cost**: ~$15-20/month for Redis + worker instance

## Verification

After setup, check logs:
- **Web service logs**: Should show "Celery task queued successfully"
- **Celery worker logs**: Should show "Verification email sent successfully"

## Troubleshooting

### Celery worker not starting
- Check environment variables are set correctly
- Verify Redis connection URL is correct
- Check worker logs for errors

### Tasks not being processed
- Verify Redis is accessible from both services
- Check `CELERY_BROKER_URL` matches Redis connection string
- Ensure worker service is running

### Emails still not sending
- Check email environment variables (EMAIL_HOST, EMAIL_HOST_USER, etc.)
- Verify SMTP credentials are correct
- Check Celery worker logs for email sending errors

