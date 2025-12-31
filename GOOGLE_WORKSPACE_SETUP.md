# Google Workspace Email Setup Guide

Quick guide for setting up Google Workspace email with Django for user verification.

## Method 1: App Passwords (Simplest - Recommended for Quick Setup)

### Step 1: Enable 2-Step Verification

1. Go to https://myaccount.google.com/security
2. Click on **2-Step Verification**
3. Follow the setup wizard to enable it
4. This is required to generate App Passwords

### Step 2: Generate App Password

1. Go to https://myaccount.google.com/apppasswords
2. Select **Mail** as the app
3. Select **Other (Custom name)** as the device
4. Enter a name like "Django App"
5. Click **Generate**
6. **Copy the 16-character password** (it looks like: `abcd efgh ijkl mnop`)
   - Remove spaces when using in Django: `abcdefghijklmnop`

### Step 3: Configure Django Environment Variables

Add to your `.env` file:

```env
# Google Workspace SMTP Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@yourdomain.com
EMAIL_HOST_PASSWORD=abcdefghijklmnop
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

**Important**:
- Replace `noreply@yourdomain.com` with your actual Google Workspace email
- Replace `abcdefghijklmnop` with your actual 16-character App Password (no spaces)
- Use the email address that matches your Google Workspace domain

### Step 4: Test Configuration

```bash
python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

# Test email
send_mail(
    subject='Test Email from LLM Diet Planner',
    message='This is a test email. If you receive this, email configuration is working!',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['your-test-email@example.com'],
    fail_silently=False,
)
```

If successful, you should see: `1` (number of emails sent) and receive the email.

## Method 2: Google Workspace Admin Console (For Organization)

If you're a Google Workspace admin managing multiple users:

### Option A: Allow App Passwords for Users

1. Go to https://admin.google.com
2. Navigate to **Security** → **Access and data control** → **API controls**
3. Under **App access control**, ensure users can use App Passwords
4. Users can then follow Method 1 above

### Option B: Enable "Less Secure App Access" (Not Recommended)

⚠️ **Security Warning**: This is less secure and Google may disable it in the future.

1. Go to https://admin.google.com
2. Navigate to **Security** → **Access and data control** → **API controls**
3. Enable "Less secure app access" for your organization
4. Users can then use their regular password (not recommended)

**Better alternative**: Use App Passwords (Method 1) or OAuth2 (see below).

## Method 3: OAuth2 (Most Secure - For Production)

For production environments, OAuth2 provides better security than App Passwords.

### Prerequisites

- Google Cloud Project
- Gmail API enabled
- OAuth2 credentials

### Setup Steps

1. **Create Google Cloud Project**:
   - Go to https://console.cloud.google.com
   - Create new project: "LLM Diet Planner Email"
   - Note the Project ID

2. **Enable Gmail API**:
   - Go to **APIs & Services** → **Library**
   - Search for "Gmail API"
   - Click **Enable**

3. **Create OAuth2 Credentials**:
   - Go to **APIs & Services** → **Credentials**
   - Click **Create Credentials** → **OAuth client ID**
   - Choose **Desktop app** (or Web application)
   - Name it "Django Email Client"
   - Click **Create**
   - Download the JSON file (save as `gmail-credentials.json`)

4. **Generate Refresh Token**:

   Install required packages:
   ```bash
   pip install google-auth google-auth-oauthlib google-auth-httplib2
   ```

   Create a script `generate_refresh_token.py`:
   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow
   import os
   
   SCOPES = ['https://www.googleapis.com/auth/gmail.send']
   CLIENT_SECRETS_FILE = 'gmail-credentials.json'
   
   flow = InstalledAppFlow.from_client_secrets_file(
       CLIENT_SECRETS_FILE, SCOPES)
   creds = flow.run_local_server(port=0)
   
   print(f"\nRefresh Token: {creds.refresh_token}")
   print(f"\nAdd this to your .env file:")
   print(f"GMAIL_API_REFRESH_TOKEN={creds.refresh_token}")
   ```

   Run it:
   ```bash
   python generate_refresh_token.py
   ```
   
   This will open a browser for authentication. After authorizing, you'll get a refresh token.

5. **Install Django Gmail Backend**:
   ```bash
   pip install django-gmailapi-backend
   ```

6. **Add to requirements.txt**:
   ```
   django-gmailapi-backend>=0.1.0
   ```

7. **Configure Django**:
   ```env
   EMAIL_BACKEND=gmailapi_backend.mail.GmailBackend
   GMAIL_API_CLIENT_ID=your-client-id-from-json.apps.googleusercontent.com
   GMAIL_API_CLIENT_SECRET=your-client-secret-from-json
   GMAIL_API_REFRESH_TOKEN=your-refresh-token-from-step-4
   DEFAULT_FROM_EMAIL=noreply@yourdomain.com
   ```

## Troubleshooting

### "Username and Password not accepted"

- ✅ Verify you're using **App Password**, not regular password
- ✅ Check that 2-Step Verification is enabled
- ✅ Ensure App Password was copied correctly (no spaces)
- ✅ Try generating a new App Password

### "Access blocked" or "Less secure app access"

- ✅ Enable 2-Step Verification and use App Passwords
- ✅ Check Google Admin Console for security policies
- ✅ Verify account isn't restricted by admin
- ✅ May need to whitelist server IP in Google Admin Console

### "Connection refused" or "Timeout"

- ✅ Check firewall allows outbound connections on port 587
- ✅ Verify `EMAIL_HOST=smtp.gmail.com` is correct
- ✅ Try port 465 with `EMAIL_USE_SSL=True` instead of TLS

### Emails going to spam

- ✅ Use a proper `DEFAULT_FROM_EMAIL` (not a personal email)
- ✅ Set up SPF and DKIM records for your domain (Google Workspace admin)
- ✅ Consider using a dedicated email like `noreply@yourdomain.com`

## Production Recommendations

1. **Use App Passwords** (Method 1) for quick setup
2. **Consider OAuth2** (Method 3) for better security in production
3. **Set up SPF/DKIM** records in Google Workspace DNS
4. **Use dedicated email** like `noreply@yourdomain.com` or `support@yourdomain.com`
5. **Monitor email delivery** in Google Workspace admin console
6. **Set up email quotas** if sending high volumes

## Quick Start (App Passwords)

For the fastest setup, use Method 1:

1. Enable 2-Step Verification
2. Generate App Password
3. Add to `.env`:
   ```env
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=noreply@yourdomain.com
   EMAIL_HOST_PASSWORD=your-16-char-app-password
   DEFAULT_FROM_EMAIL=noreply@yourdomain.com
   ```
4. Test with Django shell
5. Deploy!

