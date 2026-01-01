# Email Testing Guide

## Test Email Endpoint

After deploying, you can test email configuration using the test endpoint:

### Using cURL

```bash
curl -X POST https://your-app.ondigitalocean.app/api/auth/test-email/ \
  -H "Content-Type: application/json" \
  -d '{"to_email": "your-email@example.com"}'
```

### Using Browser DevTools Console

```javascript
fetch('/api/auth/test-email/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    to_email: 'your-email@example.com'
  })
})
.then(res => res.json())
.then(data => console.log(data))
.catch(err => console.error(err));
```

## Expected Response (Success)

```json
{
  "status": "success",
  "data": {
    "message": "Test email sent successfully to your-email@example.com",
    "email_backend": "django.core.mail.backends.smtp.EmailBackend",
    "email_host": "smtp.gmail.com",
    "from_email": "admin@zentaktestin.com"
  },
  "error": null
}
```

## Expected Response (Error)

```json
{
  "status": "error",
  "data": {
    "email_backend": "django.core.mail.backends.smtp.EmailBackend",
    "email_host": "smtp.gmail.com",
    "from_email": "admin@zentaktestin.com",
    "email_host_user_set": true,
    "email_host_password_set": false
  },
  "error": "Failed to send test email: [error message here]"
}
```

## Common Issues

### 1. Email Configuration Not Set

Check DigitalOcean App Platform environment variables:
- `EMAIL_HOST` (e.g., `smtp.gmail.com`)
- `EMAIL_HOST_USER` (your email address)
- `EMAIL_HOST_PASSWORD` (your app password or SMTP password)
- `EMAIL_PORT` (usually `587`)
- `EMAIL_USE_TLS` (`True`)
- `DEFAULT_FROM_EMAIL` (sender email)

### 2. Celery/Redis Not Working

Check logs for:
- `[DEBUG EMAIL] RegistrationView: Celery task queued successfully` - Celery is working
- `[DEBUG EMAIL] RegistrationView: Celery not available, using synchronous fallback` - Celery failed, using sync
- `[DEBUG EMAIL ERROR] RegistrationView: Synchronous email send failed` - Email config issue

### 3. Google Workspace SMTP Issues

- Use **App Password**, not regular password
- Enable 2-Step Verification first
- App Password is 16 characters (remove spaces)
- Format: `abcdefghijklmnop` (no spaces)

### 4. Check DigitalOcean Logs

Look for:
- `Starting Redis server...`
- `Redis is running successfully`
- `Starting Celery worker...`
- `Celery worker is running (PID: ...)`
- `[DEBUG EMAIL]` entries

## Diagnostic Steps

1. **Test email endpoint first** - This will show if email config is correct
2. **Check registration logs** - Look for `[DEBUG EMAIL]` entries
3. **Verify environment variables** - Make sure all email vars are set in DigitalOcean
4. **Check Celery/Redis** - Look for startup messages in logs

