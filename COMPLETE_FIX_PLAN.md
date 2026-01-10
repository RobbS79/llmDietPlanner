# Complete Fix Plan - All Issues

This plan addresses all issues identified in deploy logs and the Google OAuth silent failure.

---

## Priority 1: Google OAuth Silent Failure (CRITICAL)

### Root Cause Hypothesis
The most likely cause: `REACT_APP_GOOGLE_CLIENT_ID` is not set at **build time**.

When this happens:
1. `App.js` renders WITHOUT `GoogleOAuthProvider`
2. `GoogleLoginButton` still renders (button is visible)
3. `useGoogleLogin` hook fails silently (no provider context)
4. Clicking button does nothing - no console output, no error

### Fix 1.1: Detect Missing GoogleOAuthProvider

**File:** `frontend/src/components/GoogleLoginButton.js`

Add a context check at the top:

```javascript
import { useGoogleLogin, googleLogout } from '@react-oauth/google';
import { useContext } from 'react';

// Check if we're inside GoogleOAuthProvider
const GoogleLoginButton = ({ onSuccess, onError, text = 'Continue with Google' }) => {
  const { socialLogin } = useAuth();
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState(null);

  // Try to use the hook - if it throws, we're not inside the provider
  let googleLogin;
  let isGoogleAvailable = true;

  try {
    googleLogin = useGoogleLogin({
      // ... existing config
    });
  } catch (error) {
    isGoogleAvailable = false;
    console.error('[GoogleLogin] Google OAuth not available:', error.message);
  }

  if (!isGoogleAvailable) {
    return (
      <button type="button" className="btn-social btn-google" disabled>
        <span>Google Sign-In Not Configured</span>
      </button>
    );
  }

  // ... rest of component
};
```

### Fix 1.2: Ensure REACT_APP_GOOGLE_CLIENT_ID is Set at Build Time

**DigitalOcean App Platform Settings:**

1. Go to App Settings → Environment Variables
2. Add: `REACT_APP_GOOGLE_CLIENT_ID=392504090991-tpvagm7f3qbnv7l4u02logm30c4p4rsa.apps.googleusercontent.com`
3. **IMPORTANT:** This must be set as a **Build-time** variable, not just runtime
4. Trigger a **new build** (redeploy)

**Verification:** After deploy, check browser console for:
```
[App] Google OAuth configured with client ID: 392504090991-tpvag...
```

If you see `[App] REACT_APP_GOOGLE_CLIENT_ID is not set`, the env var is missing at build time.

### Fix 1.3: Add Startup Diagnostic Logging

**File:** `frontend/src/App.js`

Already added - logs at startup whether Google Client ID is configured.

---

## Priority 2: allauth Deprecation Warnings (MEDIUM)

### Current Warnings:
```
settings.ACCOUNT_AUTHENTICATION_METHOD is deprecated
settings.ACCOUNT_EMAIL_REQUIRED is deprecated
settings.ACCOUNT_USERNAME_REQUIRED is deprecated
```

### Fix 2.1: Update settings.py

**File:** `llm_diet_planner_project/settings.py`

Replace lines 262-276 with:

```python
# =============================================================================
# ALLAUTH & SOCIAL AUTHENTICATION CONFIGURATION
# =============================================================================

# Account settings - using new allauth 0.60+ format
ACCOUNT_LOGIN_METHODS = {'email', 'username'}  # Replaces ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']  # Replaces EMAIL_REQUIRED/USERNAME_REQUIRED
ACCOUNT_EMAIL_VERIFICATION = 'optional'  # Keep existing behavior
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https' if not DEBUG else 'http'

# Social account settings
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'  # Trust Google/Facebook verified emails
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_STORE_TOKENS = False  # Security: don't store OAuth tokens in DB
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True  # Allow login via verified email
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True  # Auto-link social accounts
```

---

## Priority 3: google.generativeai Deprecation (LOW)

### Current Warning:
```
FutureWarning: All support for the `google.generativeai` package has ended.
Please switch to the `google.genai` package.
```

### Fix 3.1: Update diet_planner/llm_service.py

**Current:**
```python
import google.generativeai as genai
```

**New:**
```python
from google import genai
```

**Note:** This requires updating the API calls as well. The new `google.genai` package has a different interface.

**Steps:**
1. Update `requirements.txt`: Replace `google-generativeai` with `google-genai`
2. Update `llm_service.py` to use new API
3. Test thoroughly

**Migration guide:** https://github.com/google-gemini/deprecated-generative-ai-python/blob/main/README.md

---

## Priority 4: Pending Migrations (LOW)

### Warning:
```
Your models in app(s): 'diet_planner', 'login_app' have changes that are not yet reflected in a migration
```

### Fix 4.1: Generate and Commit Migrations

```bash
# Run locally:
python manage.py makemigrations diet_planner login_app

# Review the generated migrations
git add diet_planner/migrations/ login_app/migrations/
git commit -m "Add missing migrations for diet_planner and login_app"
```

---

## Priority 5: Celery Worker Issues (LOW - Uses Sync Fallback)

### Warning:
```
WARNING: Celery worker may have failed to start (will use sync fallback)
```

This is non-critical - the app uses synchronous email sending as fallback. However, for production:

### Fix 5.1: Debug Celery in DigitalOcean

Check `/tmp/celery.log` for actual error. Common issues:
- Redis connection URL incorrect
- Memory limits
- Worker timeout

---

## Implementation Order

### Phase 1: Fix OAuth (Deploy ASAP)
1. ✅ GoogleLoginButton.js - Add `onNonOAuthError` handler (DONE)
2. ✅ GoogleLoginButton.js - Add visible error display (DONE)
3. ✅ social_views.py - Add debug logging (DONE)
4. ✅ App.js - Add client ID logging (DONE)
5. **Verify `REACT_APP_GOOGLE_CLIENT_ID` is set in DigitalOcean build env**
6. **Redeploy and test**

### Phase 2: Fix Deprecation Warnings
1. Update settings.py with new allauth config format
2. Test auth flows locally
3. Deploy

### Phase 3: Update google.genai (Separate PR)
1. Update requirements.txt
2. Refactor llm_service.py
3. Test LLM features
4. Deploy

### Phase 4: Housekeeping
1. Generate missing migrations
2. Review Celery logs if needed

---

## Quick Diagnostic Steps

Before deploying fixes, verify the root cause:

### Check 1: Is REACT_APP_GOOGLE_CLIENT_ID Set?

In browser console on your deployed app:
```javascript
// This won't work directly, but check console output for:
// "[App] Google OAuth configured with client ID: ..."
// OR
// "[App] REACT_APP_GOOGLE_CLIENT_ID is not set."
```

### Check 2: Is GoogleOAuthProvider Rendered?

In React DevTools, check if `GoogleOAuthProvider` appears in the component tree.

### Check 3: Network Tab

After clicking Google login and completing popup:
- Is there a `POST /api/auth/google/` request?
- If no request appears, the frontend flow is broken
- If request appears with error, check response body

### Check 4: DigitalOcean Runtime Logs

After deploying my changes and clicking Google login:
- Look for `[DEBUG OAUTH]` logs
- If no logs appear, the request never reached the backend

---

## Environment Variable Checklist

### Frontend (BUILD-TIME - must be set before build):
```
REACT_APP_GOOGLE_CLIENT_ID=392504090991-tpvagm7f3qbnv7l4u02logm30c4p4rsa.apps.googleusercontent.com
REACT_APP_API_URL=/api
```

### Backend (RUNTIME):
```
GOOGLE_CLIENT_ID=392504090991-tpvagm7f3qbnv7l4u02logm30c4p4rsa.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx
```

### Google Cloud Console:
**Authorized JavaScript Origins:**
- `https://squid-app-6avsy.ondigitalocean.app`
- `http://localhost:3000` (for local dev)

**Authorized Redirect URIs (if using auth code flow):**
- `https://squid-app-6avsy.ondigitalocean.app/accounts/google/login/callback/`
