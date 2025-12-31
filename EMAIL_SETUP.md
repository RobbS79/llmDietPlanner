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

### Option 3: Google Workspace SMTP (Recommended for Quick Setup)

Google Workspace allows you to use your business email for sending verification emails.

#### Step 1: Enable App Passwords in Google Workspace

1. **For Individual Users (if you have admin access)**:
   - Go to https://myaccount.google.com/security
   - Enable 2-Step Verification (required for App Passwords)
   - Go to https://myaccount.google.com/apppasswords
   - Generate an App Password for "Mail"
   - Copy the 16-character password (you'll use this in Django)

2. **For Google Workspace Admin (if managing organization)**:
   - Go to https://admin.google.com
   - Navigate to **Security** → **Access and data control** → **API controls**
   - Ensure "Less secure app access" is enabled (if using basic auth)
   - OR configure OAuth2 for more secure access (see OAuth2 section below)

#### Step 2: Configure Django Environment Variables

Add to your `.env` file:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@yourdomain.com
EMAIL_HOST_PASSWORD=your-16-character-app-password
DEFAULT_FROM_EMAIL=your-email@yourdomain.com
```

**Important Notes**:
- Use your **full Google Workspace email** (e.g., `noreply@yourdomain.com`)
- Use the **16-character App Password**, NOT your regular password
- App Passwords are required if 2-Step Verification is enabled
- If 2-Step Verification is disabled, you may need to enable "Less secure app access" (not recommended)

#### Step 3: Test the Configuration

```bash
python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

send_mail(
    subject='Test Email from Django',
    message='This is a test email from your Django application.',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['test@example.com'],
    fail_silently=False,
)
```

#### Troubleshooting Google Workspace

- **"Username and Password not accepted"**: 
  - Verify you're using App Password, not regular password
  - Check that 2-Step Verification is enabled
  - Ensure App Password was generated correctly

- **"Less secure app access" error**:
  - Enable 2-Step Verification and use App Passwords instead
  - OR enable "Less secure app access" in Google Admin Console (not recommended)

- **"Access blocked"**:
  - Check Google Admin Console for security policies
  - Verify the account isn't restricted by admin policies
  - May need to whitelist your server IP in Google Admin Console

### Option 3b: Google Workspace OAuth2 (More Secure, Advanced)

For production environments, OAuth2 is more secure than App Passwords.

#### Prerequisites:
1. Google Cloud Project with Gmail API enabled
2. OAuth2 credentials (Client ID and Client Secret)
3. Refresh token for your service account

#### Setup Steps:

1. **Create Google Cloud Project**:
   - Go to https://console.cloud.google.com
   - Create a new project or select existing
   - Enable "Gmail API"

2. **Create OAuth2 Credentials**:
   - Go to **APIs & Services** → **Credentials**
   - Create **OAuth 2.0 Client ID**
   - Choose "Desktop app" or "Web application"
   - Download credentials JSON

3. **Generate Refresh Token**:
   ```bash
   pip install google-auth google-auth-oauthlib google-auth-httplib2
   ```
   
   Run this script to get refresh token:
   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow
   from google.auth.transport.requests import Request
   import pickle
   
   SCOPES = ['https://www.googleapis.com/auth/gmail.send']
   
   flow = InstalledAppFlow.from_client_secrets_file(
       'credentials.json', SCOPES)
   creds = flow.run_local_server(port=0)
   
   print(f"Refresh Token: {creds.refresh_token}")
   ```

4. **Install Django Gmail Backend**:
   ```bash
   pip install django-gmailapi-backend
   ```

5. **Configure Django**:
   ```env
   EMAIL_BACKEND=gmailapi_backend.mail.GmailBackend
   GMAIL_API_CLIENT_ID=your-client-id
   GMAIL_API_CLIENT_SECRET=your-client-secret
   GMAIL_API_REFRESH_TOKEN=your-refresh-token
   DEFAULT_FROM_EMAIL=your-email@yourdomain.com
   ```

**Note**: OAuth2 setup is more complex but provides better security for production.

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

