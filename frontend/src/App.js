import React, { useState } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import LoginForm from './components/LoginForm';
import RegistrationForm from './components/RegistrationForm';
import './App.css';
import { DietaryGoalForm } from './features/diet-planner/components/DietaryGoalForm';

/**
 * Main App Content - shows different views based on auth state
 */
const AppContent = () => {
  const { isAuthenticated, user, logout, loading } = useAuth();
  const [showRegister, setShowRegister] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [createdGoal, setCreatedGoal] = useState(null);

  if (loading) {
    return (
      <div className="App">
        <div className="container" style={{ textAlign: 'center', padding: '4rem' }}>
          <p style={{ color: 'white' }}>Loading...</p>
        </div>
      </div>
    );
  }

  // Show authentication forms if not logged in
  if (!isAuthenticated) {
    return (
      <div className="App">
        <div className="auth-page">
          <div className="auth-header">
            <h1 className="App-title">LLM Diet Planner</h1>
            <p className="App-subtitle">AI-Powered Nutrition Planning</p>
          </div>
          {showRegister ? (
            <RegistrationForm
              onSwitchToLogin={() => setShowRegister(false)}
              onSuccess={() => setShowRegister(false)}
            />
          ) : (
            <LoginForm
              onSwitchToRegister={() => setShowRegister(true)}
              onSuccess={() => {
                // Login successful, will be handled by auth context
              }}
            />
          )}
        </div>
      </div>
    );
  }

  // Show dietary goal form if user clicked "Get Started"
  if (showForm) {
    return (
      <div className="App">
        <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
            <button
              onClick={() => setShowForm(false)}
              className="btn btn-secondary"
            >
              ← Back to Home
            </button>
            <button className="btn btn-secondary" onClick={logout}>
              Logout
            </button>
          </div>
          <DietaryGoalForm onSuccess={(goalData) => {
            setCreatedGoal(goalData);
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }} />
        </div>
      </div>
    );
  }

  // Show main app content when authenticated
  return (
    <div className="App">
      <header className="App-header">
        <div className="container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1 className="App-title">LLM Diet Planner</h1>
              <p className="App-subtitle">Welcome back, {user?.username}!</p>
            </div>
            <button className="btn btn-secondary" onClick={logout}>
              Logout
            </button>
          </div>
          <p className="App-description">
            Create personalised diet plans with the power of artificial intelligence.
            Get tailored meal recommendations based on your goals, preferences, and lifestyle.
          </p>
          <div className="App-actions">
            <button className="btn btn-primary" onClick={() => setShowForm(true)}>
              Get Started
            </button>
            <button className="btn btn-secondary">Learn More</button>
          </div>
        </div>
      </header>
      <main className="App-main">
        <div className="container">
          {createdGoal && (
            <div style={{
              background: '#d4edda',
              color: '#155724',
              padding: '1rem',
              borderRadius: '8px',
              marginBottom: '2rem',
              border: '1px solid #c3e6cb'
            }}>
              <strong>Success!</strong> Your dietary goal has been created. Processing will begin shortly.
            </div>
          )}
          <section className="features">
            <div className="feature-card">
              <div className="feature-icon">🍎</div>
              <h3>Personalised Plans</h3>
              <p>Customised meal plans tailored to your dietary needs and preferences</p>
            </div>
            <div className="feature-card">
              <div className="feature-icon">🤖</div>
              <h3>AI-Powered</h3>
              <p>Leverage advanced AI to create optimal nutrition strategies</p>
            </div>
            <div className="feature-card">
              <div className="feature-icon">📊</div>
              <h3>Track Progress</h3>
              <p>Monitor your nutrition goals and track your journey</p>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};

/**
 * Main App Component with Auth Provider
 */
function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
