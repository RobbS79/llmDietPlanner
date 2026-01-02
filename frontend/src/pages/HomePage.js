import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Home page - main landing page after login
 */
export function HomePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

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
            <button className="btn btn-primary" onClick={() => navigate('/create-goal')}>
              Get Started
            </button>
            <button className="btn btn-secondary" onClick={() => navigate('/goals')}>
              View My Goals
            </button>
          </div>
        </div>
      </header>
      <main className="App-main">
        <div className="container">
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
}

