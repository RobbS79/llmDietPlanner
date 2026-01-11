import React, { useState, useEffect, createContext, useContext, useCallback } from 'react';

/**
 * PRODUCTION IMPORTS
 * In your local project, uncomment these lines and delete the "PREVIEW COMPATIBILITY" block below.
 */
// import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
// import { GoogleOAuthProvider } from '@react-oauth/google';
// import { AuthProvider, useAuth } from './contexts/AuthContext';
// import { getAccessToken, getUser } from './utils/api';
// import LoginForm from './components/LoginForm';
// import RegistrationForm from './components/RegistrationForm';
// import { HomePage } from './pages/HomePage';
// import { CreateGoalPage } from './pages/CreateGoalPage';
// import { GoalsListPage } from './pages/GoalsListPage';
// import { GoalDetailPage } from './pages/GoalDetailPage';
// import { RecipePage } from './pages/RecipePage';
// import { UserProfilePage } from './pages/UserProfilePage';

// --- START OF PREVIEW COMPATIBILITY BLOCK ---
// This section allows the code to run in the Canvas preview without resolution errors.
const AuthContext = createContext({ isAuthenticated: false, loading: false, user: null });
const useAuth = () => useContext(AuthContext);
const AuthProvider = ({ children }) => <AuthContext.Provider value={{ isAuthenticated: false, loading: false }}>{children}</AuthContext.Provider>;
const GoogleOAuthProvider = ({ children }) => <>{children}</>;
const BrowserRouter = ({ children }) => <div className="router-mock">{children}</div>;
const Routes = ({ children }) => <div className="routes-mock">{children}</div>;
const Route = () => null;
const Navigate = () => null;
const useNavigate = () => (path) => console.log('Navigating to:', path);
const useLocation = () => ({ pathname: '/login', state: {} });
const getAccessToken = () => null;
const getUser = () => null;

const LoginForm = ({ onSwitchToRegister, onSuccess }) => (
  <div className="space-y-6">
    <div className="space-y-4">
       <button className="w-full flex items-center justify-center gap-3 px-4 py-2.5 border border-slate-600 rounded-xl bg-slate-700/30 text-white font-medium hover:bg-slate-700/50 transition-all">
        <svg className="w-5 h-5" viewBox="0 0 24 24">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
        </svg>
        Continue with Google
      </button>
      <div className="flex items-center gap-4 text-slate-500 text-xs uppercase tracking-wider">
        <div className="h-px flex-1 bg-slate-700"></div>
        <span>Or Email</span>
        <div className="h-px flex-1 bg-slate-700"></div>
      </div>
    </div>
    <div className="space-y-4">
      <input className="w-full bg-slate-900/50 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500/50 outline-none" placeholder="Username" />
      <input className="w-full bg-slate-900/50 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500/50 outline-none" type="password" placeholder="Password" />
    </div>
    <button onClick={onSuccess} className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-semibold shadow-lg shadow-blue-600/20 transition-all">
      Login
    </button>
    <p className="text-center text-slate-400 text-sm">
      Don't have an account? <button onClick={onSwitchToRegister} className="text-blue-400 font-medium hover:underline">Register</button>
    </p>
  </div>
);

const RegistrationForm = ({ onSwitchToLogin }) => (
  <div className="space-y-6">
    <div className="space-y-4">
      <input className="w-full bg-slate-900/50 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500/50 outline-none" placeholder="Username" />
      <input className="w-full bg-slate-900/50 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500/50 outline-none" placeholder="Email" />
      <input className="w-full bg-slate-900/50 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500/50 outline-none" type="password" placeholder="Password" />
    </div>
    <button className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-semibold shadow-lg shadow-blue-600/20 transition-all">
      Create Account
    </button>
    <p className="text-center text-slate-400 text-sm">
      Already have an account? <button onClick={onSwitchToLogin} className="text-blue-400 font-medium hover:underline">Login</button>
    </p>
  </div>
);
const HomePage = () => <div className="text-white">Home Page</div>;
// --- END OF PREVIEW COMPATIBILITY BLOCK ---

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';
const GoogleOAuthStatusContext = createContext({ scriptLoaded: false, scriptError: false });
export const useGoogleOAuthStatus = () => useContext(GoogleOAuthStatusContext);

/**
 * Protected Route
 * Declaratively handles access control and loading states.
 */
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  // Handle both state-based and storage-based auth to fix race conditions
  const hasValidSession = isAuthenticated || !!(getAccessToken() && getUser());

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#0f172a]">
        <div className="relative w-12 h-12">
          <div className="absolute top-0 left-0 w-full h-full border-4 border-blue-500/20 rounded-full"></div>
          <div className="absolute top-0 left-0 w-full h-full border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
      </div>
    );
  }

  if (!hasValidSession) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};

/**
 * Auth Layout Wrapper
 * Centralizes the authentication UI logic for Login and Register.
 */
const AuthPages = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();
  
  const isRegisterPage = location.pathname === '/register';
  const hasValidSession = isAuthenticated || !!(getAccessToken() && getUser());

  // Handle automatic redirect if already logged in
  useEffect(() => {
    if (hasValidSession) {
      const destination = location.state?.from?.pathname || '/';
      console.log('[Auth] Authenticated, navigating to:', destination);
      navigate(destination, { replace: true });
    }
  }, [hasValidSession, navigate, location.state]);

  const handleAuthSuccess = useCallback(() => {
    const destination = location.state?.from?.pathname || '/';
    // Small timeout to allow state synchronization across components
    setTimeout(() => navigate(destination, { replace: true }), 100);
  }, [navigate, location.state]);

  if (hasValidSession) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#0f172a] text-slate-400">
        Authenticating session...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0f172a] bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0f172a] to-[#020617] flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-md">
        <header className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600/10 border border-blue-500/20 mb-6 shadow-xl shadow-blue-500/5">
            <svg className="w-8 h-8 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h1 className="text-4xl font-extrabold text-white tracking-tight mb-2">LLM Diet Planner</h1>
          <p className="text-slate-400 text-lg font-medium">AI-Powered Nutrition Strategy</p>
        </header>
        
        <main className="bg-slate-800/40 backdrop-blur-xl border border-slate-700/50 p-8 rounded-[2.5rem] shadow-2xl">
          {isRegisterPage ? (
            <RegistrationForm 
              onSwitchToLogin={() => navigate('/login', { state: location.state })}
              onSuccess={() => navigate('/login', { state: { ...location.state, message: 'Account created! Please login.' }})}
            />
          ) : (
            <LoginForm 
              onSwitchToRegister={() => navigate('/register', { state: location.state })}
              onSuccess={handleAuthSuccess}
            />
          )}
        </main>
        
        <footer className="mt-12 text-center">
           <p className="text-slate-500 text-xs uppercase tracking-[0.2em] font-semibold">
            &copy; {new Date().getFullYear()} LLM Diet Planner Systems
          </p>
        </footer>
      </div>
    </div>
  );
};

/**
 * Application Routes
 */
const AppContent = () => {
  return (
    <Routes>
      <Route path="/login" element={<AuthPages />} />
      <Route path="/register" element={<AuthPages />} />
      
      <Route path="/" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
      
      {/* Add your other routes here following the ProtectedRoute pattern:
        <Route path="/profile" element={<ProtectedRoute><UserProfilePage /></ProtectedRoute>} />
      */}

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

/**
 * Root Application Component
 */
export default function App() {
  const [googleStatus, setGoogleStatus] = useState({
    scriptLoaded: false,
    scriptError: false
  });

  return (
    <GoogleOAuthProvider
      clientId={GOOGLE_CLIENT_ID || "placeholder-id.apps.googleusercontent.com"}
      onScriptLoadError={() => setGoogleStatus({ scriptLoaded: false, scriptError: true })}
      onScriptLoadSuccess={() => setGoogleStatus({ scriptLoaded: true, scriptError: false })}
    >
      <GoogleOAuthStatusContext.Provider value={googleStatus}>
        <AuthProvider>
          <BrowserRouter>
            <div className="font-sans antialiased text-slate-200">
              {/* For preview, we show the AuthPages directly */}
              <AuthPages /> 
            </div>
          </BrowserRouter>
        </AuthProvider>
      </GoogleOAuthStatusContext.Provider>
    </GoogleOAuthProvider>
  );
}