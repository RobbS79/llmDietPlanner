# Google OAuth Fix Plan

## Problem Summary
Error: `redirect_uri_mismatch` with `origin=https://squid-app-6avsy.ondigitalocean.app`

The Google OAuth 2.0 Client is misconfigured in Google Cloud Console.

---

## Step 1: Fix Google Cloud Console (REQUIRED)

### 1.1 Update Authorized JavaScript Origins
**Current**: `https://your-app-name.ondigitalocean.app` (placeholder - WRONG)
**Change to**: `https://squid-app-6avsy.ondigitalocean.app`

### 1.2 Review Authorized Redirect URIs
Depending on which OAuth flow you want to use:

**Option A - Implicit Flow (Recommended for SPAs)**
- Frontend uses Google Sign-In JavaScript library
- User clicks "Sign in with Google" → Google popup → Frontend gets `access_token`
- Frontend POSTs `{ "access_token": "..." }` to `/api/auth/google/`
- **No redirect URIs needed** - only JavaScript origins

**Option B - Authorization Code Flow**
- User clicks "Sign in with Google" → Redirected to Google → Redirected back to your app
- Requires redirect URI: `https://squid-app-6avsy.ondigitalocean.app/accounts/google/login/callback/`

---

## Step 2: Django Configuration Changes

### If using Option A (Implicit Flow) - No Django changes needed
Your current setup already supports this. Just fix Google Console.

### If using Option B (Authorization Code Flow)
Add allauth URLs to `llm_diet_planner_project/urls.py`:

```python
urlpatterns = [
    # ... existing urls ...
    path("accounts/", include("allauth.urls")),  # Add this for OAuth callbacks
]
```

And update Google Console redirect URIs to:
- `https://squid-app-6avsy.ondigitalocean.app/accounts/google/login/callback/`

---

## Step 3: Environment Variables Check

Ensure these are set in DigitalOcean App Platform:

```
GOOGLE_CLIENT_ID=392504090991-tpvagm7f3qbnv7l4u02logm30c4p4rsa.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<your-secret>
GOOGLE_CALLBACK_URL=https://squid-app-6avsy.ondigitalocean.app/accounts/google/login/callback/
```

Note: `GOOGLE_CALLBACK_URL` is only needed for authorization code flow.

---

## Recommended Action Summary

1. **Google Cloud Console**:
   - Go to: https://console.cloud.google.com/apis/credentials
   - Edit OAuth 2.0 Client ID
   - Change JavaScript origin: `https://your-app-name.ondigitalocean.app` → `https://squid-app-6avsy.ondigitalocean.app`
   - Add redirect URI if using auth code flow: `https://squid-app-6avsy.ondigitalocean.app/accounts/google/login/callback/`

2. **Wait 5-15 minutes** for Google to propagate changes

3. **Test again**

---

## Frontend Implementation Notes

### For Implicit Flow (Option A)
Your React frontend should use `@react-oauth/google`:

```javascript
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';

// On successful Google login:
const handleGoogleSuccess = async (credentialResponse) => {
  const response = await fetch('/api/auth/google/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      access_token: credentialResponse.credential
    })
  });
  const data = await response.json();
  // Store JWT tokens from data.data.access and data.data.refresh
};
```

### For Authorization Code Flow (Option B)
Redirect user to Google, then handle callback server-side.
