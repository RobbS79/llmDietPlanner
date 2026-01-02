import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import LoginForm from './components/LoginForm';
import RegistrationForm from './components/RegistrationForm';
import { HomePage } from './pages/HomePage';
import { CreateGoalPage } from './pages/CreateGoalPage';
import { GoalsListPage } from './pages/GoalsListPage';
import { GoalDetailPage } from './pages/GoalDetailPage';
import { UserProfilePage } from './pages/UserProfilePage';
import './App.css';

/**
 * Protected Route Component - redirects to login if not authenticated
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

  if (!isAuthenticated) {
    // Redirect to login with return path
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};

/**
 * Auth Pages Component - handles login/register
 */
const AuthPages = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();
  const isRegisterPage = location.pathname === '/register';

  // If already authenticated, redirect to home
  if (isAuthenticated) {
    const from = location.state?.from?.pathname || '/';
    return <Navigate to={from} replace />;
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
            onSuccess={() => {
              // Navigate to the page they were trying to access, or home
              const from = location.state?.from?.pathname || '/';
              navigate(from, { replace: true });
            }}
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
 */
function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
