# OAuth Setup Guide for Google and Facebook Authentication

This guide explains how to set up OAuth credentials for Google and Facebook social authentication in the LLM Diet Planner application.

## Overview

The application uses `django-allauth` and `dj-rest-auth` for OAuth2 authentication. You need to:

1. Create OAuth applications on Google Cloud Console and Facebook Developers
2. Configure the credentials as environment variables
3. Set up redirect/callback URLs

## Google OAuth Setup

### Step 1: Create a Project in Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google+ API** or **Google Identity API**

### Step 2: Create OAuth 2.0 Credentials

1. Navigate to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: External (for public apps) or Internal (for G Suite)
   - App name: "LLM Diet Planner" (or your app name)
   - User support email: Your email
   - Developer contact: Your email
   - Scopes: `email`, `profile`, `openid`
   - Test users: Add your email for testing (if in testing mode)

4. Create OAuth Client ID:
   - Application type: **Web application**
   - Name: "LLM Diet Planner Backend"
   - **Authorized JavaScript origins:**
     - `http://localhost:8000` (for development)
     - `http://localhost:3000` (for frontend dev server)
     - `https://your-production-domain.com` (for production)
   - **Authorized redirect URIs:**
     - `http://localhost:8000/api/auth/google/callback/` (for development)
     - `https://your-production-domain.com/api/auth/google/callback/` (for production)
     - Note: If using frontend OAuth flow, also add frontend URLs

5. Copy the **Client ID** and **Client Secret**

### Step 3: Configure Environment Variables

Add to your `.env` file or environment:

```bash
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_CALLBACK_URL=http://localhost:8000/api/auth/google/callback/  # Optional for authorization code flow
```

For production:

```bash
GOOGLE_CLIENT_ID=your-production-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-production-client-secret
GOOGLE_CALLBACK_URL=https://your-production-domain.com/api/auth/google/callback/
```

## Facebook OAuth Setup

### Step 1: Create a Facebook App

1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Click **My Apps** → **Create App**
3. Choose app type: **Consumer** or **Business** (recommended for production)
4. Fill in app details:
   - App Display Name: "LLM Diet Planner"
   - App Contact Email: Your email
   - Purpose: "To provide a personalised diet planning service"

### Step 2: Add Facebook Login Product

1. In your app dashboard, click **Add Product**
2. Find **Facebook Login** and click **Set Up**
3. Select **Web** as the platform
4. Configure **Settings** → **Basic**:
   - **App Domains**: Add your domains (e.g., `localhost`, `your-production-domain.com`)
   - **Privacy Policy URL**: Your privacy policy URL
   - **Terms of Service URL**: Your terms of service URL
   - **User Data Deletion**: URL for data deletion requests (GDPR compliance)

5. In **Facebook Login** → **Settings**:
   - **Valid OAuth Redirect URIs**:
     - `http://localhost:8000/api/auth/facebook/callback/` (development)
     - `https://your-production-domain.com/api/auth/facebook/callback/` (production)
     - If using frontend flow, also add: `http://localhost:3000/auth/facebook/callback/`

6. In **Settings** → **Basic**, copy:
   - **App ID**
   - **App Secret** (click Show and copy)

### Step 3: Request Permissions

Facebook Login → **Permissions and Features**:
- Request `email` permission (required)
- Request `public_profile` permission (default, includes name, profile picture)

### Step 4: Configure Environment Variables

Add to your `.env` file or environment:

```bash
FACEBOOK_APP_ID=your-facebook-app-id
FACEBOOK_APP_SECRET=your-facebook-app-secret
FACEBOOK_CALLBACK_URL=http://localhost:8000/api/auth/facebook/callback/  # Optional for authorization code flow
```

For production:

```bash
FACEBOOK_APP_ID=your-production-app-id
FACEBOOK_APP_SECRET=your-production-app-secret
FACEBOOK_CALLBACK_URL=https://your-production-domain.com/api/auth/facebook/callback/
```

## Testing OAuth Authentication

### Frontend Integration

The backend expects one of these request formats:

**Option 1: Using access_token (recommended for frontend OAuth SDKs)**

```javascript
// After user authenticates with Google/Facebook SDK on frontend
const response = await fetch('/api/auth/google/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    access_token: googleAccessToken  // From Google SDK
  })
});

const data = await response.json();
// Response format: { "status": "success", "data": { "access": "...", "refresh": "...", "user": {...} }, "error": null }
```

**Option 2: Using authorization code**

```javascript
const response = await fetch('/api/auth/google/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    code: authorizationCode,  // From OAuth redirect
    redirect_uri: 'http://localhost:3000/auth/callback'
  })
});
```

### Testing with curl

```bash
# Test Google OAuth (replace with actual access token)
curl -X POST http://localhost:8000/api/auth/google/ \
  -H "Content-Type: application/json" \
  -d '{"access_token": "your-google-access-token"}'

# Test Facebook OAuth (replace with actual access token)
curl -X POST http://localhost:8000/api/auth/facebook/ \
  -H "Content-Type: application/json" \
  -d '{"access_token": "your-facebook-access-token"}'
```

## Database Migration

Ensure allauth social account tables are created:

```bash
python manage.py migrate
```

If you see migrations for `socialaccount`, `socialaccount_socialaccount`, etc., they should be applied automatically.

## Troubleshooting

### "OAuth credentials are not configured"

- Check that environment variables are set correctly
- Verify variable names match exactly: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`
- Restart your Django server after setting environment variables

### "Invalid access token" or "Authentication failed"

- Verify the access token is valid and not expired
- Check that the OAuth app is in "Live" mode (not Development) for production
- Ensure redirect URIs match exactly (including trailing slashes)
- For Facebook: Verify app is not in Development mode restrictions

### "Redirect URI mismatch"

- Check that callback URLs in OAuth provider settings exactly match those in your environment
- Include both HTTP (development) and HTTPS (production) versions
- Ensure trailing slashes are consistent

### Account linking issues

- If a user with the same email already exists, the social account will be automatically linked
- The user's `primary_auth_provider` will only change if it was previously "email"
- Check logs for messages about account creation vs. linking

## Production Checklist

- [ ] OAuth apps are in "Live" mode (Facebook) or published (Google)
- [ ] All redirect URIs use HTTPS
- [ ] Environment variables are set securely (use secrets management, not `.env` in production)
- [ ] Privacy Policy and Terms of Service URLs are configured (Facebook requirement)
- [ ] App domains are correctly configured
- [ ] Test OAuth flow end-to-end in production environment
- [ ] Monitor logs for authentication errors

## Security Notes

- **Never commit** `.env` files or credentials to version control
- Use environment variables or secrets management in production (AWS Secrets Manager, HashiCorp Vault, etc.)
- The application is configured to **not store OAuth tokens** in the database (`SOCIALACCOUNT_STORE_TOKENS = False`)
- OAuth tokens are only used temporarily for authentication and user creation
- All social authentication requires email verification by the provider (trusted sources)

## Additional Resources

- [django-allauth Documentation](https://docs.allauth.org/)
- [dj-rest-auth Documentation](https://dj-rest-auth.readthedocs.io/)
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Facebook Login Documentation](https://developers.facebook.com/docs/facebook-login/)

