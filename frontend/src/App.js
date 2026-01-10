import React, { useState, useEffect, createContext, useContext } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { getAccessToken, getUser } from './utils/api';
import LoginForm from './components/LoginForm';
import RegistrationForm from './components/RegistrationForm';
import { HomePage } from './pages/HomePage';
import { CreateGoalPage } from './pages/CreateGoalPage';
import { GoalsListPage } from './pages/GoalsListPage';
import { GoalDetailPage } from './pages/GoalDetailPage';
import { RecipePage } from './pages/RecipePage';
import { UserProfilePage } from './pages/UserProfilePage';
import './App.css';

// Google OAuth Client ID from environment variable
const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

// Log warning if Google OAuth is not configured (helpful for debugging)
if (!GOOGLE_CLIENT_ID) {
  console.warn('[App] REACT_APP_GOOGLE_CLIENT_ID is not set. Google OAuth will be disabled.');
  console.warn('[App] To enable Google OAuth:');
  console.warn('  1. Set REACT_APP_GOOGLE_CLIENT_ID in your .env file');
  console.warn('  2. Rebuild the frontend (npm run build or restart npm start)');
} else {
  console.log('[App] Google OAuth configured with client ID:', GOOGLE_CLIENT_ID.substring(0, 20) + '...');
  // Validate format
  if (!GOOGLE_CLIENT_ID.endsWith('.apps.googleusercontent.com')) {
    console.error('[App] WARNING: Client ID format appears invalid. Expected format: xxx.apps.googleusercontent.com');
  }
}

// Context to share Google OAuth script load status
const GoogleOAuthStatusContext = createContext({ scriptLoaded: false, scriptError: false });
export const useGoogleOAuthStatus = () => useContext(GoogleOAuthStatusContext);

/**
 * Protected Route Component - redirects to login if not authenticated
 *
 * Checks both React state AND localStorage to handle the race condition
 * where tokens are stored but React state hasn't updated yet (e.g., after OAuth login)
 */
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="App">
        <div className="container" style={{ textAlign: 'center', padding: '4rem' }}>
          <p style={{ color: 'white' }}>Loading...</p>
        </div>
      </div>
    );
  }

  // Check both React state AND localStorage for authentication
  // This handles the race condition where tokens are stored but state hasn't updated yet
  const hasTokensInStorage = !!(getAccessToken() && getUser());
  const hasValidSession = isAuthenticated || hasTokensInStorage;

  if (!hasValidSession) {
    // Redirect to login with return path
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};

/**
 * Auth Pages Component - handles login/register
 *
 * Uses useEffect to handle navigation after successful login/OAuth
 * to avoid race conditions with React state updates.
 */
const AuthPages = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();
  const isRegisterPage = location.pathname === '/register';
  const [loginAttempted, setLoginAttempted] = useState(false);

  // Check both React state AND localStorage for authentication
  // This handles the race condition where tokens are stored but state hasn't updated yet
  const hasTokensInStorage = !!(getAccessToken() && getUser());
  const hasValidSession = isAuthenticated || hasTokensInStorage;

  // Use useEffect to navigate after state updates
  // This ensures navigation happens AFTER React has processed state changes
  useEffect(() => {
    if (hasValidSession) {
      const from = location.state?.from?.pathname || '/';
      console.log('[Auth] User authenticated, redirecting to:', from);
      navigate(from, { replace: true });
    }
  }, [hasValidSession, navigate, location.state]);

  // Also navigate when login is attempted and tokens exist
  // This handles the case where state hasn't updated but tokens are in localStorage
  useEffect(() => {
    if (loginAttempted && hasTokensInStorage) {
      const from = location.state?.from?.pathname || '/';
      console.log('[Auth] Login successful (tokens in storage), redirecting to:', from);
      navigate(from, { replace: true });
    }
  }, [loginAttempted, hasTokensInStorage, navigate, location.state]);

  // Handle successful login - just mark login as attempted
  // The useEffect above will handle the actual navigation
  const handleLoginSuccess = () => {
    console.log('[Auth] Login success callback triggered');
    setLoginAttempted(true);
    // Also force a small delay to allow state to propagate
    setTimeout(() => {
      const token = getAccessToken();
      const user = getUser();
      console.log('[Auth] After login - Token exists:', !!token, 'User exists:', !!user);
      if (token && user) {
        const from = location.state?.from?.pathname || '/';
        navigate(from, { replace: true });
      }
    }, 100);
  };

  // If already authenticated, show loading briefly then redirect
  if (hasValidSession) {
    return (
      <div className="App">
        <div className="container" style={{ textAlign: 'center', padding: '4rem' }}>
          <p style={{ color: 'white' }}>Redirecting...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="App">
      <div className="auth-page">
        <div className="auth-header">
          <h1 className="App-title">LLM Diet Planner</h1>
          <p className="App-subtitle">AI-Powered Nutrition Planning</p>
        </div>
        {isRegisterPage ? (
          <RegistrationForm
            onSwitchToLogin={() => navigate('/login', { state: location.state })}
            onSuccess={() => {
              // After successful registration, navigate to login
              navigate('/login', {
                state: {
                  ...location.state,
                  message: 'Registration successful! Please login.'
                }
              });
            }}
          />
        ) : (
          <LoginForm
            onSwitchToRegister={() => navigate('/register', { state: location.state })}
            onSuccess={handleLoginSuccess}
          />
        )}
      </div>
    </div>
  );
};

/**
 * Main App Content with Routing
 */
const AppContent = () => {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<AuthPages />} />
      <Route path="/register" element={<AuthPages />} />

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <HomePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/create-goal"
        element={
          <ProtectedRoute>
            <CreateGoalPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/goals"
        element={
          <ProtectedRoute>
            <GoalsListPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/goals/:goalId"
        element={
          <ProtectedRoute>
            <GoalDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/recipe/:mealIdentifier"
        element={
          <ProtectedRoute>
            <RecipePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <UserProfilePage />
          </ProtectedRoute>
        }
      />

      {/* Catch all - redirect to home */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

/**
 * Main App Component with Auth Provider and Router
 * Conditionally wraps with GoogleOAuthProvider only if client ID is configured
 */
function App() {
  const [googleOAuthStatus, setGoogleOAuthStatus] = useState({
    scriptLoaded: false,
    scriptError: false
  });

  // If no Google client ID is configured, render without GoogleOAuthProvider
  if (!GOOGLE_CLIENT_ID) {
    return (
      <GoogleOAuthStatusContext.Provider value={{ scriptLoaded: false, scriptError: false, clientIdMissing: true }}>
        <AuthProvider>
          <BrowserRouter>
            <AppContent />
          </BrowserRouter>
        </AuthProvider>
      </GoogleOAuthStatusContext.Provider>
    );
  }

  return (
    <GoogleOAuthProvider
      clientId={GOOGLE_CLIENT_ID}
      onScriptLoadError={() => {
        console.error('[App] Google OAuth script failed to load');
        console.error('[App] This may be due to network issues or content blockers');
        setGoogleOAuthStatus({ scriptLoaded: false, scriptError: true });
      }}
      onScriptLoadSuccess={() => {
        console.log('[App] Google OAuth script loaded successfully');
        console.log('[App] Current origin:', window.location.origin);
        console.log('[App] Make sure this origin is added to Google Cloud Console JavaScript origins');
        setGoogleOAuthStatus({ scriptLoaded: true, scriptError: false });
      }}
    >
      <GoogleOAuthStatusContext.Provider value={googleOAuthStatus}>
        <AuthProvider>
          <BrowserRouter>
            <AppContent />
          </BrowserRouter>
        </AuthProvider>
      </GoogleOAuthStatusContext.Provider>
    </GoogleOAuthProvider>
  );
}

export default App;
