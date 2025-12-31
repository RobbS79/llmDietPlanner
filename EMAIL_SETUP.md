# Email Configuration Guide

This guide explains how to set up email sending for user verification in production.

## Current Configuration

The application uses Django's email backend with the following settings (from `settings.py`):

- **Development (DEBUG=True)**: Uses `console.EmailBackend` (emails printed to console)
- **Production (DEBUG=False)**: Uses `smtp.EmailBackend` (requires SMTP server)

## Required Environment Variables

Add these to your `.env` file or production environment:

```env
# Email Backend (optional - defaults to SMTP in production)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend

# SMTP Server Configuration
EMAIL_HOST=smtp.your-email-provider.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@yourdomain.com
EMAIL_HOST_PASSWORD=your-email-password-or-app-password

# Sender Email Address
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

## Email Service Options

### Option 1: SendGrid (Recommended for Production)

1. Sign up at https://sendgrid.com
2. Create an API key
3. Verify your sender email/domain
4. Configure:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key-here
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

### Option 2: Mailgun

1. Sign up at https://www.mailgun.com
2. Verify your domain
3. Get SMTP credentials
4. Configure:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=postmaster@yourdomain.mailgun.org
EMAIL_HOST_PASSWORD=your-mailgun-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

### Option 3: Gmail SMTP (For Testing/Development)

⚠️ **Not recommended for production** - use a proper email service instead.

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-specific-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
```

**Note**: You'll need to enable "App Passwords" in your Google Account settings.

### Option 4: AWS SES (Amazon Simple Email Service)

1. Set up AWS SES
2. Verify your email/domain
3. Get SMTP credentials
4. Configure:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=email-smtp.region.amazonaws.com  # Replace 'region' with your AWS region
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-aws-smtp-username
EMAIL_HOST_PASSWORD=your-aws-smtp-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

## Celery Configuration (Required)

Emails are sent asynchronously via Celery. Make sure:

1. **Redis is running** (for Celery broker):
```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

2. **Celery worker is running**:
```bash
celery -A llm_diet_planner_project worker --loglevel=info
```

Or in production with Docker, add a Celery service to your `docker-compose.prod.yml`.

## Testing Email Configuration

### Test in Django Shell

```bash
python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

send_mail(
    subject='Test Email',
    message='This is a test email.',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['your-email@example.com'],
    fail_silently=False,
)
```

### Test Registration Flow

1. Register a new user via the frontend
2. Check Celery logs for email task execution
3. Verify email is received
4. Click verification link to activate account

## Troubleshooting

### Emails Not Sending

1. **Check Celery is running**: `celery -A llm_diet_planner_project inspect active`
2. **Check email backend**: Verify `EMAIL_BACKEND` in settings
3. **Check SMTP credentials**: Verify all email environment variables are set
4. **Check logs**: Look for email-related errors in Django/Celery logs
5. **Test SMTP connection**: Use the Django shell test above

### Common Issues

- **"Authentication failed"**: Check `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`
- **"Connection refused"**: Check `EMAIL_HOST` and `EMAIL_PORT`
- **"Email not verified"**: For services like SendGrid/Mailgun, verify your sender email/domain first
- **"Celery task not executing"**: Ensure Celery worker is running and Redis is accessible

## Production Checklist

- [ ] Email service account created (SendGrid/Mailgun/AWS SES)
- [ ] Sender email/domain verified
- [ ] Environment variables configured in production
- [ ] Redis configured and running
- [ ] Celery worker running in production
- [ ] Test email sent successfully
- [ ] Registration flow tested end-to-end

## Security Notes

- Never commit email credentials to git
- Use environment variables or secrets management
- Use app-specific passwords, not main account passwords
- Consider using Django's email backend with encryption for sensitive data

