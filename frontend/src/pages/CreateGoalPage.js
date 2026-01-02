import React from 'react';
import { useNavigate } from 'react-router-dom';
import { DietaryGoalForm } from '../features/diet-planner/components/DietaryGoalForm';
import { Navigation } from '../components/Navigation';

/**
 * Page for creating a new dietary goal
 */
export function CreateGoalPage() {
  const navigate = useNavigate();

  return (
    <div className="App">
      <Navigation />
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        <div style={{ marginBottom: '2rem' }}>
          <button
            onClick={() => navigate('/goals')}
            className="btn btn-secondary"
          >
            ← Back to Goals
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

