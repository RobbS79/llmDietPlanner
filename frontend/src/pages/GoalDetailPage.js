import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getAccessToken } from '../utils/api';

/**
 * Page for viewing details of a specific dietary goal
 */
export function GoalDetailPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { goalId } = useParams();
  const [goal, setGoal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Fetch goal details
    const fetchGoal = async () => {
      try {
        const token = getAccessToken();
        const headers = {
          'Content-Type': 'application/json',
        };
        
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`/api/goals/${goalId}/`, {
          headers,
          credentials: 'include',
        });
        
        if (!response.ok) {
          throw new Error('Failed to load goal');
        }
        
        const data = await response.json();
        if (data.status === 'success') {
          setGoal(data.data);
        } else {
          throw new Error(data.error || 'Failed to load goal');
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (goalId) {
      fetchGoal();
    }
  }, [goalId]);

  return (
    <div className="App">
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
          <button
            onClick={() => navigate('/goals')}
            className="btn btn-secondary"
          >
            ← Back to Goals
          </button>
          <button className="btn btn-secondary" onClick={logout}>
            Logout
          </button>
        </div>

        {loading && (
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <p>Loading goal details...</p>
          </div>
        )}

        {error && (
          <div style={{
            background: '#f8d7da',
            color: '#721c24',
            padding: '1rem',
            borderRadius: '8px',
            marginBottom: '2rem',
            border: '1px solid #f5c6cb'
          }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {goal && (
          <div style={{ background: 'white', padding: '2rem', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
            <h2>Goal #{goal.id}</h2>
            <p><strong>Status:</strong> {goal.status}</p>
            <p><strong>Location:</strong> {goal.city}, {goal.country}</p>
            <p><strong>Currency:</strong> {goal.currency}</p>
            <p><strong>Language:</strong> {goal.language_code}</p>
            <p><strong>Created:</strong> {new Date(goal.created_at).toLocaleString()}</p>
            
            {goal.dietary_plan && (
              <div style={{ marginTop: '2rem', paddingTop: '2rem', borderTop: '1px solid #ddd' }}>
                <h3>Dietary Plan</h3>
                <pre style={{ background: '#f5f5f5', padding: '1rem', borderRadius: '4px', overflow: 'auto' }}>
                  {JSON.stringify(goal.dietary_plan, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

