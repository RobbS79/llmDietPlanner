# DigitalOcean App Platform - Email Configuration

## Quick Setup

Since email worked on `develop` branch, you already have the correct email credentials. You just need to add them to DigitalOcean App Platform for the `prod` branch.

## Step 1: Add Email Environment Variables

In DigitalOcean App Platform dashboard:

1. Go to your app → **Settings** → **App-Level Environment Variables**
2. Add these variables (same values you used for develop):

### Required Variables:

- **EMAIL_HOST**
  - Value: `smtp.gmail.com` (if using Google Workspace)
  - Type: `SECRET` (recommended)
  - Scope: `RUN_TIME`

- **EMAIL_HOST_USER**
  - Value: Your email address (e.g., `admin@zentaktestin.com`)
  - Type: `SECRET` (recommended)
  - Scope: `RUN_TIME`

- **EMAIL_HOST_PASSWORD**
  - Value: Your App Password (16 characters, no spaces)
  - Type: `SECRET` (required - hide this!)
  - Scope: `RUN_TIME`

- **DEFAULT_FROM_EMAIL**
  - Value: `admin@zentaktestin.com` (or your sender email)
  - Type: `SECRET` (optional, can be plain text)
  - Scope: `RUN_TIME`

### Optional Variables (with defaults):

- **EMAIL_BACKEND**: `django.core.mail.backends.smtp.EmailBackend` (default)
- **EMAIL_PORT**: `587` (default)
- **EMAIL_USE_TLS**: `True` (default)

## Step 2: Verify Configuration

After adding the variables, the `.do/app.yaml` file has been updated to include these variables. You can either:

**Option A: Use app.yaml (recommended)**
- The variables are defined in `.do/app.yaml`
- DigitalOcean will use them (but you still need to set the actual secret values in the UI)

**Option B: Set in UI only**
- Just add them in the DigitalOcean dashboard
- They'll override the app.yaml defaults

## Step 3: Test

After adding the variables:

1. Redeploy the app (or wait for auto-deploy if enabled)
2. Test using the test endpoint: `POST /api/auth/test-email/`
3. Or register a new user and check if email arrives

## Google Workspace Setup Reminder

If using Google Workspace (which you are, based on `admin@zentaktestin.com`):

1. Make sure you have an **App Password** (not your regular password)
2. Enable **2-Step Verification** first (required for App Passwords)
3. Generate App Password at: https://myaccount.google.com/apppasswords
4. Use the 16-character password (remove spaces)

## Troubleshooting

- **"Authentication failed"**: Wrong password or not using App Password
- **"Connection refused"**: Check EMAIL_HOST is correct
- **"Email not sent"**: Check all environment variables are set
- **Check logs**: Look for `[DEBUG EMAIL]` entries in DigitalOcean logs

