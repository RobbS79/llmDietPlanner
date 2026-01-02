import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useDietaryGoalsList } from '../features/diet-planner/hooks/useDietaryGoals';

/**
 * Page for listing all dietary goals
 */
export function GoalsListPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: goalsResponse, isLoading, error } = useDietaryGoalsList();
  // API returns { status: "success", data: [...] }
  const goals = goalsResponse?.status === 'success' ? goalsResponse.data : [];

  const successMessage = location.state?.message;

  return (
    <div className="App">
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
          <h1 style={{ margin: 0 }}>My Dietary Goals</h1>
          <div>
            <button
              onClick={() => navigate('/create-goal')}
              className="btn btn-primary"
              style={{ marginRight: '10px' }}
            >
              + Create New Goal
            </button>
            <button className="btn btn-secondary" onClick={logout}>
              Logout
            </button>
          </div>
        </div>

        {successMessage && (
          <div style={{
            background: '#d4edda',
            color: '#155724',
            padding: '1rem',
            borderRadius: '8px',
            marginBottom: '2rem',
            border: '1px solid #c3e6cb'
          }}>
            <strong>Success!</strong> {successMessage}
          </div>
        )}

        {isLoading && (
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <p>Loading your goals...</p>
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
            <strong>Error:</strong> {error.message || 'Failed to load goals'}
          </div>
        )}

        {!isLoading && !error && goals && (
          <>
            {goals.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '3rem' }}>
                <p style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>No dietary goals yet</p>
                <button
                  onClick={() => navigate('/create-goal')}
                  className="btn btn-primary"
                >
                  Create Your First Goal
                </button>
              </div>
            ) : (
              <div style={{ display: 'grid', gap: '1rem' }}>
                {goals.map((goal) => (
                  <div
                    key={goal.id}
                    style={{
                      background: 'white',
                      padding: '1.5rem',
                      borderRadius: '8px',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                      cursor: 'pointer',
                      transition: 'transform 0.2s',
                    }}
                    onClick={() => navigate(`/goals/${goal.id}`)}
                    onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-2px)'}
                    onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                      <div>
                        <h3 style={{ margin: '0 0 0.5rem 0' }}>Goal #{goal.id}</h3>
                        <p style={{ margin: '0.5rem 0', color: '#666' }}>
                          <strong>Status:</strong> <span style={{ 
                            color: goal.status === 'completed' ? '#28a745' : 
                                   goal.status === 'processing' ? '#ffc107' : 
                                   goal.status === 'failed' ? '#dc3545' : '#6c757d'
                          }}>{goal.status}</span>
                        </p>
                        <p style={{ margin: '0.5rem 0', color: '#666' }}>
                          <strong>Location:</strong> {goal.city}, {goal.country}
                        </p>
                        <p style={{ margin: '0.5rem 0', color: '#666' }}>
                          <strong>Created:</strong> {new Date(goal.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <button
                        className="btn btn-secondary"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/goals/${goal.id}`);
                        }}
                      >
                        View Details →
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

