import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { DietaryGoalForm } from '../features/diet-planner/components/DietaryGoalForm';

/**
 * Page for creating a new dietary goal
 */
export function CreateGoalPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="App">
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
          <button
            onClick={() => navigate('/')}
            className="btn btn-secondary"
          >
            ← Back to Home
          </button>
          <button className="btn btn-secondary" onClick={logout}>
            Logout
          </button>
        </div>
        <DietaryGoalForm onSuccess={(goalData) => {
          // Navigate to goals list after successful creation
          navigate('/goals', { state: { message: 'Dietary goal created successfully! Processing will begin shortly.' } });
        }} />
      </div>
    </div>
  );
}

