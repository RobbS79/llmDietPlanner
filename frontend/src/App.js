import React, { useState } from 'react';
import './App.css';
import { DietaryGoalForm } from './features/diet-planner/components/DietaryGoalForm';

function App() {
  const [showForm, setShowForm] = useState(false);
  const [createdGoal, setCreatedGoal] = useState(null);

  const handleGetStarted = () => {
    setShowForm(true);
  };

  const handleFormSuccess = (goalData) => {
    setCreatedGoal(goalData);
    // Optionally scroll to show success message
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleBackToHome = () => {
    setShowForm(false);
    setCreatedGoal(null);
  };

  if (showForm) {
    return (
      <div className="App">
        <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
          <button
            onClick={handleBackToHome}
            className="btn btn-secondary"
            style={{ marginBottom: '2rem' }}
          >
            ← Back to Home
          </button>
          <DietaryGoalForm onSuccess={handleFormSuccess} />
        </div>
      </div>
    );
  }

  return (
    <div className="App">
      <header className="App-header">
        <div className="container">
          <h1 className="App-title">LLM Diet Planner</h1>
          <p className="App-subtitle">AI-Powered Nutrition Planning</p>
          <p className="App-description">
            Create personalised diet plans with the power of artificial intelligence.
            Get tailored meal recommendations based on your goals, preferences, and lifestyle.
          </p>
          <div className="App-actions">
            <button className="btn btn-primary" onClick={handleGetStarted}>
              Get Started
            </button>
            <button className="btn btn-secondary">Learn More</button>
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

export default App;

