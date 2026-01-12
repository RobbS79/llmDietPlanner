import React, { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { setTokens } from '../utils/api';

/**
 * LoginSuccess Component
 * Path: frontend/src/pages/LoginSuccess.js
 * * This page handles the redirect from the Django backend.
 * It extracts JWT tokens from the URL parameters, saves them to localStorage,
 * and then redirects the user to the dashboard.
 */
export function LoginSuccess() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    // Parse query parameters from the URL
    const params = new URLSearchParams(location.search);
    const access = params.get('access');
    const refresh = params.get('refresh');

    if (access && refresh) {
      console.log("[Auth] Google tokens successfully received. Finalizing session...");
      
      // Save tokens using the utility function
      setTokens(access, refresh);
      
      // Force a hard redirect to the home page to ensure AuthContext 
      // picks up the changes and updates the user state.
      window.location.href = '/'; 
    } else {
      console.error("[Auth] Authentication failed: No tokens found in redirect URL.");
      navigate('/login', { state: { error: "Google authentication failed. Please try again." } });
    }
  }, [location, navigate]);

  return (
    <div className="App" style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      height: '100vh', 
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white' 
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔐</div>
        <h2>Authenticating...</h2>
        <p>We are finalizing your secure session. You will be redirected shortly.</p>
      </div>
    </div>
  );
}