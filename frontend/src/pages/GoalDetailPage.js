import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getAccessToken } from '../utils/api';
import { Navigation } from '../components/Navigation';

/**
 * Page for viewing details of a specific dietary goal
 */
export function GoalDetailPage() {
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

  const getStatusBadge = (status) => {
    const statusColors = {
      pending: { bg: '#fef3c7', text: '#92400e', border: '#fbbf24' },
      processing: { bg: '#dbeafe', text: '#1e40af', border: '#3b82f6' },
      completed: { bg: '#d1fae5', text: '#065f46', border: '#10b981' },
      failed: { bg: '#fee2e2', text: '#991b1b', border: '#ef4444' },
    };
    const colors = statusColors[status] || statusColors.pending;
    return (
      <span style={{
        display: 'inline-block',
        padding: '0.25rem 0.75rem',
        borderRadius: '9999px',
        fontSize: '0.875rem',
        fontWeight: '600',
        background: colors.bg,
        color: colors.text,
        border: `1px solid ${colors.border}`,
        textTransform: 'capitalize',
      }}>
        {status}
      </span>
    );
  };

  return (
    <div className="App">
      <Navigation />
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        {loading && (
          <div style={{ textAlign: 'center', padding: '4rem' }}>
            <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⏳</div>
            <p style={{ color: '#6b7280' }}>Loading goal details...</p>
          </div>
        )}

        {error && (
          <div style={{
            background: '#fee2e2',
            color: '#991b1b',
            padding: '1rem 1.5rem',
            borderRadius: '8px',
            marginBottom: '2rem',
            border: '1px solid #fca5a5',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}>
            <span>❌</span>
            <div>
              <strong>Error:</strong> {error}
            </div>
          </div>
        )}

        {goal && (
          <div style={{
            background: 'white',
            padding: '2rem',
            borderRadius: '12px',
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
          }}>
            {/* Header */}
            <div style={{ marginBottom: '2rem', paddingBottom: '1.5rem', borderBottom: '2px solid #e5e7eb' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <h1 style={{ margin: 0, fontSize: '2rem', color: '#1f2937' }}>Goal #{goal.id}</h1>
                {getStatusBadge(goal.status)}
              </div>
              <button
                onClick={() => navigate('/goals')}
                className="btn btn-secondary"
                style={{ marginTop: '0.5rem' }}
              >
                ← Back to Goals
              </button>
            </div>

            {/* Goal Info */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '1rem',
              marginBottom: '2rem',
            }}>
              <div style={{ padding: '1rem', background: '#f9fafb', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Location</div>
                <div style={{ fontWeight: '600', color: '#1f2937' }}>{goal.city}, {goal.country}</div>
              </div>
              <div style={{ padding: '1rem', background: '#f9fafb', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Currency</div>
                <div style={{ fontWeight: '600', color: '#1f2937' }}>{goal.currency}</div>
              </div>
              <div style={{ padding: '1rem', background: '#f9fafb', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Language</div>
                <div style={{ fontWeight: '600', color: '#1f2937' }}>{goal.language_code}</div>
              </div>
              <div style={{ padding: '1rem', background: '#f9fafb', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Created</div>
                <div style={{ fontWeight: '600', color: '#1f2937' }}>
                  {new Date(goal.created_at).toLocaleDateString()}
                </div>
              </div>
            </div>

            {/* Dietary Plan */}
            {goal.dietary_plan ? (
              <div style={{ marginTop: '2rem', paddingTop: '2rem', borderTop: '2px solid #e5e7eb' }}>
                <h2 style={{ marginBottom: '1.5rem', color: '#1f2937' }}>📋 Dietary Plan</h2>
                
                {/* Meal Ideas */}
                {goal.dietary_plan.meal_ideas && goal.dietary_plan.meal_ideas.length > 0 && (
                  <div style={{ marginBottom: '2rem' }}>
                    <h3 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.25rem' }}>🍽️ Meal Ideas</h3>
                    <div style={{ display: 'grid', gap: '1rem' }}>
                      {goal.dietary_plan.meal_ideas.map((meal, index) => (
                        <div
                          key={index}
                          style={{
                            padding: '1.5rem',
                            background: '#f9fafb',
                            borderRadius: '8px',
                            border: '1px solid #e5e7eb',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                            <h4 style={{ margin: 0, fontSize: '1.125rem', color: '#1f2937' }}>{meal.name}</h4>
                            {meal.preparation_time && (
                              <span style={{
                                padding: '0.25rem 0.75rem',
                                background: '#dbeafe',
                                color: '#1e40af',
                                borderRadius: '9999px',
                                fontSize: '0.875rem',
                                fontWeight: '500',
                              }}>
                                ⏱️ {meal.preparation_time} min
                              </span>
                            )}
                          </div>
                          {meal.description && (
                            <p style={{ margin: '0 0 0.75rem 0', color: '#6b7280', fontSize: '0.9rem' }}>
                              {meal.description}
                            </p>
                          )}
                          {meal.ingredients && meal.ingredients.length > 0 && (
                            <div style={{ marginBottom: '0.75rem' }}>
                              <div style={{ fontSize: '0.875rem', fontWeight: '600', color: '#4b5563', marginBottom: '0.5rem' }}>
                                Ingredients:
                              </div>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                {meal.ingredients.map((ingredient, i) => (
                                  <span
                                    key={i}
                                    style={{
                                      padding: '0.25rem 0.75rem',
                                      background: 'white',
                                      border: '1px solid #d1d5db',
                                      borderRadius: '6px',
                                      fontSize: '0.875rem',
                                      color: '#374151',
                                    }}
                                  >
                                    {ingredient}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          {meal.nutritional_info && (
                            <div style={{
                              padding: '0.75rem',
                              background: 'white',
                              borderRadius: '6px',
                              border: '1px solid #e5e7eb',
                            }}>
                              <div style={{ fontSize: '0.875rem', fontWeight: '600', color: '#4b5563', marginBottom: '0.5rem' }}>
                                Nutritional Info:
                              </div>
                              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                                {meal.nutritional_info.calories && (
                                  <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                    🔥 {meal.nutritional_info.calories} cal
                                  </span>
                                )}
                                {meal.nutritional_info.protein && (
                                  <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                    💪 {meal.nutritional_info.protein}
                                  </span>
                                )}
                                {meal.nutritional_info.carbs && (
                                  <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                    🍞 {meal.nutritional_info.carbs}
                                  </span>
                                )}
                                {meal.nutritional_info.fat && (
                                  <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                    🥑 {meal.nutritional_info.fat}
                                  </span>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Shopping List */}
                {goal.dietary_plan.shopping_list && goal.dietary_plan.shopping_list.length > 0 && (
                  <div>
                    <h3 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.25rem' }}>🛒 Shopping List</h3>
                    <div style={{
                      padding: '1.5rem',
                      background: '#f9fafb',
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                    }}>
                      <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {goal.dietary_plan.shopping_list.map((item, index) => (
                          <div
                            key={index}
                            style={{
                              padding: '1rem',
                              background: 'white',
                              borderRadius: '6px',
                              border: '1px solid #e5e7eb',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <div style={{ flex: 1 }}>
                              <div style={{ fontWeight: '600', color: '#1f2937', marginBottom: '0.25rem' }}>
                                {item.ingredient}
                              </div>
                              {item.notes && (
                                <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                  {item.notes}
                                </div>
                              )}
                            </div>
                            {(item.quantity || item.unit) && (
                              <div style={{
                                padding: '0.5rem 1rem',
                                background: '#eff6ff',
                                borderRadius: '6px',
                                fontWeight: '600',
                                color: '#1e40af',
                                fontSize: '0.875rem',
                              }}>
                                {item.quantity} {item.unit}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Total Price */}
                {goal.dietary_plan.total_price && (
                  <div style={{
                    marginTop: '1.5rem',
                    padding: '1rem',
                    background: '#d1fae5',
                    borderRadius: '8px',
                    border: '1px solid #10b981',
                    textAlign: 'center',
                  }}>
                    <div style={{ fontSize: '0.875rem', color: '#065f46', marginBottom: '0.25rem' }}>
                      Total Estimated Price
                    </div>
                    <div style={{ fontSize: '1.5rem', fontWeight: '700', color: '#065f46' }}>
                      {goal.dietary_plan.total_price} {goal.dietary_plan.currency || goal.currency}
                    </div>
                  </div>
                )}

                {(!goal.dietary_plan.meal_ideas || goal.dietary_plan.meal_ideas.length === 0) &&
                 (!goal.dietary_plan.shopping_list || goal.dietary_plan.shopping_list.length === 0) && (
                  <div style={{
                    padding: '2rem',
                    textAlign: 'center',
                    color: '#6b7280',
                    background: '#f9fafb',
                    borderRadius: '8px',
                    border: '1px dashed #d1d5db',
                  }}>
                    <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📝</div>
                    <p>No meal ideas or shopping list available yet.</p>
                  </div>
                )}
              </div>
            ) : (
              <div style={{
                marginTop: '2rem',
                padding: '2rem',
                textAlign: 'center',
                background: '#fef3c7',
                borderRadius: '8px',
                border: '1px solid #fbbf24',
              }}>
                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>⏳</div>
                <p style={{ margin: 0, color: '#92400e' }}>
                  Dietary plan is still being generated. Please check back soon!
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

