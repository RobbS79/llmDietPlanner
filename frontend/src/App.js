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
import { LoginSuccess } from './pages/LoginSuccess';
import './App.css';

/**
 * Protected Route Wrapper
 */
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="App"><p style={{ color: 'white', textAlign: 'center', padding: '4rem' }}>Loading...</p></div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};

/**
 * Shared layout for Auth pages
 */
const AuthPages = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();
  const isRegisterPage = location.pathname === '/register';

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
            onSuccess={() => navigate('/login', { state: { message: 'Registration successful! Please login.' } })}
          />
        ) : (
          <LoginForm
            onSwitchToRegister={() => navigate('/register', { state: location.state })}
            onSuccess={() => {
              const from = location.state?.from?.pathname || '/';
              navigate(from, { replace: true });
            }}
          />
        )}
      </div>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Authentication Routes */}
          <Route path="/login" element={<AuthPages />} />
          <Route path="/register" element={<AuthPages />} />
          
          {/* Oauth2 Callback Route */}
          <Route path="/login-success" element={<LoginSuccess />} />
          
          {/* Protected Application Routes */}
          <Route path="/" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
          <Route path="/create-goal" element={<ProtectedRoute><CreateGoalPage /></ProtectedRoute>} />
          <Route path="/goals" element={<ProtectedRoute><GoalsListPage /></ProtectedRoute>} />
          <Route path="/goals/:goalId" element={<ProtectedRoute><GoalDetailPage /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute><UserProfilePage /></ProtectedRoute>} />
          
          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;