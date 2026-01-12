import React, { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { setTokens } from '../utils/api';

/**
 * Handles processing of JWT tokens after Google callback.
 */
export function LoginSuccess() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const access = params.get('access');
    const refresh = params.get('refresh');

    if (access && refresh) {
      setTokens(access, refresh);
      console.log("[Auth] Google Login successful. Redirecting...");
      window.location.href = '/'; 
    } else {
      console.error("[Auth] Failed to parse tokens from callback URL.");
      navigate('/login');
    }
  }, [location, navigate]);

  return (
    <div style={{ textAlign: 'center', padding: '5rem', color: 'white' }}>
      <h2>Authenticating...</h2>
      <p>Finalizing your session, please wait.</p>
    </div>
  );
}