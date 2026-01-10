/**
 * Google Login Button Component
 * Uses @react-oauth/google to handle Google OAuth
 */
import React, { useState, useCallback } from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { useAuth } from '../contexts/AuthContext';

// Check if Google OAuth is configured at build time
const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID;

const GoogleLoginButton = ({ onSuccess, onError, text = 'Continue with Google' }) => {
  const { socialLogin } = useAuth();
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState(null);

  // Memoize the success handler to avoid recreating on every render
  const handleGoogleSuccess = useCallback(async (tokenResponse) => {
    console.log('[GoogleLogin] Google OAuth success, token response:', {
      access_token: tokenResponse.access_token ? 'present' : 'missing',
      credential: tokenResponse.credential ? 'present' : 'missing',
      token_type: tokenResponse.token_type,
      expires_in: tokenResponse.expires_in,
    });
    setLocalError(null);
    setLoading(true);

    // Check if we actually got an access token
    if (!tokenResponse.access_token) {
      const errMsg = 'Google did not return an access token. Please try again.';
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
        setLocalError(null);
        if (onSuccess) onSuccess(result.data);
      } else {
        const errMsg = result.error || 'Google login failed. Please try again.';
        console.error('[GoogleLogin] Login failed:', errMsg);
        setLocalError(errMsg);
        if (onError) onError(errMsg);
      }
    } catch (error) {
      const errMsg = error.message || 'An unexpected error occurred during Google login.';
      console.error('[GoogleLogin] Exception during login:', error);
      setLocalError(errMsg);
      if (onError) onError(errMsg);
    } finally {
      setLoading(false);
    }
  }, [socialLogin, onSuccess, onError]);

  const handleGoogleError = useCallback((error) => {
    console.error('[GoogleLogin] Google OAuth error:', error);
    // Google Identity Services error structure
    const errorMsg = error?.error_description || error?.error || 'Google sign-in was cancelled or failed';
    setLocalError(errorMsg);
    if (onError) onError(errorMsg);
  }, [onError]);

  const handleNonOAuthError = useCallback((error) => {
    // This catches popup closed, popup blocked, etc.
    console.error('[GoogleLogin] Non-OAuth error:', error);
    let errorMsg;
    if (error?.type === 'popup_closed') {
      errorMsg = 'Google sign-in popup was closed. Please try again.';
    } else if (error?.type === 'popup_failed_to_open') {
      errorMsg = 'Could not open Google sign-in popup. Please check your popup blocker settings.';
    } else {
      errorMsg = 'Google sign-in failed to initialize. Please refresh and try again.';
    }
    setLocalError(errorMsg);
    if (onError) onError(errorMsg);
  }, [onError]);

  // Hook must be called unconditionally (React rules of hooks)
  // When GOOGLE_CLIENT_ID is not set, this hook will not work but we handle that in the UI
  const googleLogin = useGoogleLogin({
    onSuccess: handleGoogleSuccess,
    onError: handleGoogleError,
    onNonOAuthError: handleNonOAuthError,
    flow: 'implicit',  // Explicitly set flow type
    prompt: 'select_account',  // Force account selection to avoid silent failures
  });

  // If Google OAuth is not configured, show disabled button
  // This check is done AFTER all hooks are called to comply with React rules
  if (!GOOGLE_CLIENT_ID) {
    console.warn('[GoogleLogin] REACT_APP_GOOGLE_CLIENT_ID is not configured. Google OAuth disabled.');
    return (
      <div className="google-login-wrapper">
        <button
          type="button"
          className="btn-social btn-google"
          disabled
          title="Google Sign-In is not configured"
        >
          <svg className="social-icon" viewBox="0 0 24 24" width="20" height="20">
            <path fill="#999" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#999" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#999" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#999" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          <span>Google Sign-In Unavailable</span>
        </button>
        <p className="google-login-error" style={{
          color: '#6c757d',
          fontSize: '0.75rem',
          marginTop: '0.5rem',
          textAlign: 'center'
        }}>
          Google Sign-In is not configured
        </p>
      </div>
    );
  }

  return (
    <div className="google-login-wrapper">
      <button
        type="button"
        className="btn-social btn-google"
        onClick={() => {
          console.log('[GoogleLogin] Button clicked, initiating OAuth flow...');
          console.log('[GoogleLogin] Client ID configured:', GOOGLE_CLIENT_ID ? GOOGLE_CLIENT_ID.substring(0, 20) + '...' : 'NOT SET');
          setLocalError(null);
          try {
            googleLogin();
            console.log('[GoogleLogin] googleLogin() called successfully, popup should open');
          } catch (err) {
            console.error('[GoogleLogin] Error calling googleLogin():', err);
            setLocalError('Failed to start Google sign-in: ' + err.message);
          }
        }}
        disabled={loading}
      >
        <svg className="social-icon" viewBox="0 0 24 24" width="20" height="20">
          <path
            fill="#4285F4"
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
          />
          <path
            fill="#34A853"
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
          />
          <path
            fill="#FBBC05"
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
          />
          <path
            fill="#EA4335"
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
          />
        </svg>
        <span>{loading ? 'Signing in...' : text}</span>
      </button>
      {localError && (
        <p className="google-login-error" style={{
          color: '#dc3545',
          fontSize: '0.875rem',
          marginTop: '0.5rem',
          textAlign: 'center'
        }}>
          {localError}
        </p>
      )}
    </div>
  );
};

export default GoogleLoginButton;
