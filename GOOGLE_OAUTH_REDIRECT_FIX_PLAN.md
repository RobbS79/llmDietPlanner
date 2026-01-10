# Google OAuth Complete Fix Plan

## Problem Summary
After successful Google OAuth popup handling, nothing happens on the login page:
- No redirect to dashboard
- No error message displayed
- No console output visible

This indicates a **silent OAuth failure** - the flow breaks somewhere without any user feedback.

---

## Root Cause Analysis

### Possible Failure Points

1. **Google OAuth popup returns but callbacks don't fire**
   - `@react-oauth/google`'s `useGoogleLogin` may not call `onSuccess` or `onError`
   - Caused by: Google Console misconfiguration (JavaScript origins mismatch)

2. **Frontend receives token but backend call fails silently**
   - POST to `/api/auth/google/` fails with CORS error or network error
   - Error is caught but not displayed to user

3. **Backend processes token but returns error**
   - dj-rest-auth/allauth fails to validate the access token
   - Google Client ID/Secret mismatch between frontend and backend

4. **Race condition in React state updates**
   - Tokens stored but React state not updated
   - Navigation triggered before auth state is ready

---

## Phase 1: Diagnosis (Do This First!)

### Step 1.1: Check Browser DevTools Network Tab

Before any code changes, reproduce the issue and check:

1. Open browser DevTools → Network tab
2. Clear network log
3. Click "Sign in with Google" and complete OAuth flow
4. Look for:
   - `POST /api/auth/google/` request - did it happen?
   - Response status code (200, 400, 401, 500?)
   - Response body - any error messages?
   - CORS errors in console?

### Step 1.2: Check Browser DevTools Console

Look for:
- JavaScript errors (red text)
- `[GoogleLogin]` logs (should appear if callback fires)
- `[AuthContext]` logs
- `[API]` logs

### Step 1.3: Check Google Cloud Console Configuration

Verify at https://console.cloud.google.com/apis/credentials:

1. **Authorized JavaScript Origins** must include:
   - `https://squid-app-6avsy.ondigitalocean.app`
   - `http://localhost:3000` (for local dev)

2. **Authorized Redirect URIs** (only if using auth code flow):
   - `https://squid-app-6avsy.ondigitalocean.app/accounts/google/login/callback/`

3. **Client ID matches** what's in your environment variables:
   - Frontend: `REACT_APP_GOOGLE_CLIENT_ID`
   - Backend: `GOOGLE_CLIENT_ID`

### Step 1.4: Check Environment Variables

**Frontend (.env or DigitalOcean env vars):**
```
REACT_APP_GOOGLE_CLIENT_ID=392504090991-tpvagm7f3qbnv7l4u02logm30c4p4rsa.apps.googleusercontent.com
```

**Backend (DigitalOcean env vars):**
```
GOOGLE_CLIENT_ID=392504090991-tpvagm7f3qbnv7l4u02logm30c4p4rsa.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<your-secret>
```

**CRITICAL**: Frontend and backend MUST use the SAME Google Client ID!

---

## Phase 2: Add Visible Error Handling

The current implementation only logs to console. Add user-visible error messages.

### Fix 2.1: Update GoogleLoginButton.js - Add Error State Propagation

**File:** `frontend/src/components/GoogleLoginButton.js`

**Problem:** Errors are logged but user sees nothing.

**Current onError handler (line 35-38):**
```javascript
onError: (error) => {
  console.error('[GoogleLogin] Google OAuth error:', error);
  if (onError) onError('Google login was cancelled or failed');
},
```

**Issue:** Google's new Identity Services library doesn't always call onError for all failure types.

**Fix - Add more robust error handling:**
```javascript
import React, { useState, useEffect } from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { useAuth } from '../contexts/AuthContext';

const GoogleLoginButton = ({ onSuccess, onError, text = 'Continue with Google' }) => {
  const { socialLogin } = useAuth();
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState(null);

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      console.log('[GoogleLogin] Google OAuth success, token type:', tokenResponse.token_type);
      setLocalError(null);
      setLoading(true);

      // Check if we actually got an access token
      if (!tokenResponse.access_token) {
        const errMsg = 'Google did not return an access token';
        console.error('[GoogleLogin] Error:', errMsg);
        setLocalError(errMsg);
        if (onError) onError(errMsg);
        setLoading(false);
        return;
      }

      try {
        console.log('[GoogleLogin] Calling socialLogin with access token...');
        const result = await socialLogin('google', tokenResponse.access_token);
        console.log('[GoogleLogin] socialLogin result:', {
          success: result.success,
          hasData: !!result.data,
          error: result.error
        });

        if (result.success) {
          console.log('[GoogleLogin] Login successful, calling onSuccess callback');
          if (onSuccess) onSuccess(result.data);
        } else {
          const errMsg = result.error || 'Google login failed';
          console.error('[GoogleLogin] Login failed:', errMsg);
          setLocalError(errMsg);
          if (onError) onError(errMsg);
        }
      } catch (error) {
        const errMsg = error.message || 'An unexpected error occurred';
        console.error('[GoogleLogin] Exception during login:', error);
        setLocalError(errMsg);
        if (onError) onError(errMsg);
      } finally {
        setLoading(false);
      }
    },
    onError: (error) => {
      console.error('[GoogleLogin] Google OAuth error:', error);
      // Google Identity Services error structure
      const errorMsg = error?.error_description || error?.error || 'Google sign-in was cancelled or failed';
      setLocalError(errorMsg);
      if (onError) onError(errorMsg);
    },
    onNonOAuthError: (error) => {
      // This catches popup closed, popup blocked, etc.
      console.error('[GoogleLogin] Non-OAuth error:', error);
      const errorMsg = error?.type === 'popup_closed'
        ? 'Google sign-in popup was closed'
        : 'Google sign-in failed to initialize';
      setLocalError(errorMsg);
      if (onError) onError(errorMsg);
    },
  });

  return (
    <div>
      <button
        type="button"
        className="btn-social btn-google"
        onClick={() => {
          setLocalError(null);
          googleLogin();
        }}
        disabled={loading}
      >
        {/* SVG icon */}
        <span>{loading ? 'Signing in...' : text}</span>
      </button>
      {localError && (
        <p style={{ color: '#dc3545', fontSize: '0.875rem', marginTop: '0.5rem' }}>
          {localError}
        </p>
      )}
    </div>
  );
};

export default GoogleLoginButton;
```

### Fix 2.2: Update LoginForm.js - Display Social Login Errors

**File:** `frontend/src/components/LoginForm.js`

**Current handleSocialError (line 25-27):**
```javascript
const handleSocialError = (errorMessage) => {
  setError(errorMessage || 'Social login failed. Please try again.');
};
```

**This is correct**, but ensure `error` state is being displayed. Check line 60:
```javascript
{error && <div className="auth-error">{error}</div>}
```

This should work. The issue is likely that `onError` is never called.

### Fix 2.3: Add Backend Debug Logging

**File:** `login_app/social_views.py`

Add more verbose logging to trace the OAuth flow:

```python
@method_decorator(csrf_exempt, name='dispatch')
class GoogleLogin(StandardizedSocialLoginView):
    # ... existing code ...

    def post(self, request, *args, **kwargs):
        import sys
        print(f"[DEBUG OAUTH] GoogleLogin.post: Request received", file=sys.stderr, flush=True)
        print(f"[DEBUG OAUTH] GoogleLogin.post: Request data keys: {list(request.data.keys())}", file=sys.stderr, flush=True)
        print(f"[DEBUG OAUTH] GoogleLogin.post: Has access_token: {'access_token' in request.data}", file=sys.stderr, flush=True)

        # Check credentials
        if not self._check_credentials_configured():
            print(f"[DEBUG OAUTH] GoogleLogin.post: Credentials not configured!", file=sys.stderr, flush=True)
            return Response(...)

        print(f"[DEBUG OAUTH] GoogleLogin.post: Credentials OK, calling parent...", file=sys.stderr, flush=True)

        try:
            response = super().post(request, *args, **kwargs)
            print(f"[DEBUG OAUTH] GoogleLogin.post: Parent returned status {response.status_code}", file=sys.stderr, flush=True)
            print(f"[DEBUG OAUTH] GoogleLogin.post: Response data: {response.data}", file=sys.stderr, flush=True)
            # ... rest of existing code
        except Exception as e:
            print(f"[DEBUG OAUTH] GoogleLogin.post: Exception: {e}", file=sys.stderr, flush=True)
            import traceback
            print(f"[DEBUG OAUTH] GoogleLogin.post: Traceback: {traceback.format_exc()}", file=sys.stderr, flush=True)
            raise
```

---

## Phase 3: Fix Token Flow Issues

### Fix 3.1: Ensure Google Client ID is Available to Frontend

**File:** `frontend/src/App.js`

**Problem (lines 17, 221-229):**
```javascript
const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

// If no Google client ID, render without GoogleOAuthProvider
if (!GOOGLE_CLIENT_ID) {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </AuthProvider>
  );
}
```

**Risk:** If `REACT_APP_GOOGLE_CLIENT_ID` isn't set at BUILD time (not runtime), the button will appear but OAuth won't work.

**Add a warning in development:**
```javascript
const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

// Log warning if Google OAuth is not configured
if (!GOOGLE_CLIENT_ID) {
  console.warn('[App] REACT_APP_GOOGLE_CLIENT_ID is not set. Google OAuth will be disabled.');
}
```

### Fix 3.2: Handle Missing GoogleOAuthProvider Gracefully

When `GOOGLE_CLIENT_ID` is empty, `useGoogleLogin` will fail silently because there's no provider.

**Update GoogleLoginButton.js to detect this:**
```javascript
import { useGoogleLogin, hasGrantedAllScopesGoogle } from '@react-oauth/google';

const GoogleLoginButton = ({ onSuccess, onError, text = 'Continue with Google' }) => {
  // Check if we're inside GoogleOAuthProvider
  let googleLogin;
  try {
    googleLogin = useGoogleLogin({
      // ... config
    });
  } catch (e) {
    // Not inside GoogleOAuthProvider
    return (
      <button type="button" className="btn-social btn-google" disabled>
        <span>Google Sign-In Not Available</span>
      </button>
    );
  }
  // ...
};
```

---

## Phase 4: Fix Race Condition (Already Partially Implemented)

The existing code in App.js already handles the race condition:

```javascript
// Check both React state AND localStorage for authentication
const hasTokensInStorage = !!(getAccessToken() && getUser());
const hasValidSession = isAuthenticated || hasTokensInStorage;
```

However, there may be a timing issue. Add a small delay after login success:

### Fix 4.1: Update AuthContext socialLogin to Ensure State Sync

**File:** `frontend/src/contexts/AuthContext.js`

```javascript
const socialLogin = async (provider, accessToken) => {
  try {
    console.log('[AuthContext] socialLogin called for provider:', provider);
    let response;
    if (provider === 'google') {
      response = await authAPI.googleLogin(accessToken);
    } else if (provider === 'facebook') {
      response = await authAPI.facebookLogin(accessToken);
    } else {
      throw new Error(`Unknown provider: ${provider}`);
    }

    console.log('[AuthContext] API response received');

    const userData = response.data?.user || getUser();

    if (!userData) {
      console.error('[AuthContext] No user data available after login');
      return { success: false, error: 'No user data received from server' };
    }

    console.log('[AuthContext] Setting user state:', { username: userData?.username });
    setUserState(userData);

    // Wait a tick for state to propagate
    await new Promise(resolve => setTimeout(resolve, 50));

    // Fetch profile to ensure all data is loaded
    await fetchProfile();

    console.log('[AuthContext] Profile fetched, returning success');
    return { success: true, data: response.data };
  } catch (error) {
    console.error('[AuthContext] socialLogin error:', error.message);
    return { success: false, error: error.message };
  }
};
```

---

## Phase 5: Backend Token Validation Issues

### Common Issue: Wrong Token Type

`@react-oauth/google`'s `useGoogleLogin` returns an **access token** (for Google APIs).
However, `GoogleLogin` component returns an **ID token** (credential).

**Check what token type is being sent:**

In `api.js`, the `googleLogin` function sends:
```javascript
body: JSON.stringify({ access_token: accessToken }),
```

The backend's `GoogleOAuth2Adapter` expects an access token, which is correct.

**However**, if you're using the `GoogleLogin` component (not `useGoogleLogin`), you get a `credential` (ID token), not an access token!

### Fix 5.1: Verify Token Type

**In GoogleLoginButton.js:**
```javascript
console.log('[GoogleLogin] Token response:', {
  access_token: tokenResponse.access_token ? 'present' : 'missing',
  credential: tokenResponse.credential ? 'present' : 'missing',
  token_type: tokenResponse.token_type,
  expires_in: tokenResponse.expires_in,
});
```

If `access_token` is missing but `credential` is present, you need to:
1. Use `credential` instead (requires backend changes), or
2. Use `useGoogleLogin` hook (current approach - should work)

---

## Quick Fixes Checklist

- [ ] Check Network tab for `/api/auth/google/` request
- [ ] Check Console for any JavaScript errors
- [ ] Verify `REACT_APP_GOOGLE_CLIENT_ID` is set in build environment
- [ ] Verify Google Console JavaScript Origins include your domain
- [ ] Add `onNonOAuthError` handler to GoogleLoginButton
- [ ] Add visible error display in GoogleLoginButton
- [ ] Check backend logs (DigitalOcean Runtime Logs) for OAuth errors

---

## Testing After Fixes

1. **Clear browser localStorage** before testing
2. **Hard refresh** the page (Cmd+Shift+R or Ctrl+Shift+R)
3. **Open DevTools** before clicking Google login
4. Click "Sign in with Google"
5. Complete Google OAuth in popup
6. **Check:**
   - Console logs appear?
   - Network request to `/api/auth/google/` made?
   - Error message displayed on page?
   - Redirected to dashboard?

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/components/GoogleLoginButton.js` | Add `onNonOAuthError`, local error state, visible error display |
| `frontend/src/contexts/AuthContext.js` | Add state sync delay, better error handling |
| `frontend/src/App.js` | Add warning when Google Client ID missing |
| `login_app/social_views.py` | Add debug logging |

---

## Environment Variables Checklist

### Frontend (set at BUILD time):
```
REACT_APP_GOOGLE_CLIENT_ID=your-client-id
REACT_APP_API_URL=/api
```

### Backend (set at runtime):
```
GOOGLE_CLIENT_ID=same-client-id-as-frontend
GOOGLE_CLIENT_SECRET=your-client-secret
```

---

## If Nothing Works - Alternative Approach

If the `useGoogleLogin` hook continues to fail silently, consider switching to the `GoogleLogin` component which has better error handling:

```javascript
import { GoogleLogin } from '@react-oauth/google';

<GoogleLogin
  onSuccess={(credentialResponse) => {
    // credentialResponse.credential is an ID token, not access token
    // Backend needs to handle ID token validation differently
    console.log('Success:', credentialResponse);
  }}
  onError={() => {
    console.log('Login Failed');
    setError('Google login failed');
  }}
/>
```

This requires backend changes to validate ID tokens instead of access tokens.
