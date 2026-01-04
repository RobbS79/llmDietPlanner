import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getAccessToken } from '../utils/api';
import { Navigation } from '../components/Navigation';
import { generateMealIdentifier, getMealInstance } from '../features/diet-planner/utils/api';

/**
 * Page for viewing details of a specific dietary goal
 */
export function GoalDetailPage() {
  const navigate = useNavigate();
  const { goalId } = useParams();
  const [goal, setGoal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [cookedMeals, setCookedMeals] = useState({});

  useEffect(() => {
    // Fetch goal details with token refresh handling
    const fetchGoal = async () => {
      try {
        const { getAccessToken, getRefreshToken, setTokens, clearTokens } = await import('../utils/api');
        let token = getAccessToken();
        let headers = {
          'Content-Type': 'application/json',
        };
        
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        let response = await fetch(`/api/goals/${goalId}/`, {
          headers,
          credentials: 'include',
        });
        
        // Handle 401 - token expired, try to refresh
        if (response.status === 401) {
          const refreshToken = getRefreshToken();
          if (refreshToken) {
            try {
              const refreshResponse = await fetch('/api/auth/refresh/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh: refreshToken }),
              });

              if (refreshResponse.ok) {
                const refreshData = await refreshResponse.json();
                const newAccessToken = refreshData.access || refreshData.data?.access;
                if (newAccessToken) {
                  setTokens(newAccessToken, refreshToken);
                  // Retry with new token
                  headers['Authorization'] = `Bearer ${newAccessToken}`;
                  response = await fetch(`/api/goals/${goalId}/`, {
                    headers,
                    credentials: 'include',
                  });
                }
              }
            } catch (refreshError) {
              // Refresh failed, clear tokens and redirect to login
              clearTokens();
              window.location.href = '/login';
              return;
            }
          } else {
            // No refresh token, redirect to login
            clearTokens();
            window.location.href = '/login';
            return;
          }
        }
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          if (response.status === 401) {
            clearTokens();
            window.location.href = '/login';
            return;
          }
          throw new Error(errorData.detail || errorData.error || 'Failed to load goal');
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
            {(() => {
              const plan = goal.dietary_plan;
              const hasDays = plan?.days && Array.isArray(plan.days) && plan.days.length > 0;
              const hasMealIdeas = plan?.meal_ideas && Array.isArray(plan.meal_ideas) && plan.meal_ideas.length > 0; // Legacy support
              const hasShoppingList = plan?.shopping_list && Array.isArray(plan.shopping_list) && plan.shopping_list.length > 0;
              
              // Helper function to render a meal
              const renderMeal = (meal, index, dayNumber, mealType) => {
                if (!meal) return null;
                
                const mealIdentifier = generateMealIdentifier(goal.id, dayNumber, mealType, index);
                const isCooked = cookedMeals[mealIdentifier] || false;
                
                return (
                  <div
                    key={index}
                    onClick={() => navigate(`/recipe/${encodeURIComponent(mealIdentifier)}`)}
                    style={{
                      padding: '1.5rem',
                      background: isCooked ? '#f0fdf4' : '#f9fafb',
                      borderRadius: '8px',
                      border: isCooked ? '2px solid #10b981' : '1px solid #e5e7eb',
                      marginBottom: '1rem',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.transform = 'translateY(-2px)';
                      e.currentTarget.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = 'translateY(0)';
                      e.currentTarget.style.boxShadow = 'none';
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                      <div style={{ flex: 1 }}>
                        <h4 style={{ margin: 0, fontSize: '1.125rem', color: '#1f2937', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          {meal.name}
                          {isCooked && (
                            <span style={{
                              padding: '0.25rem 0.5rem',
                              background: '#10b981',
                              color: 'white',
                              borderRadius: '9999px',
                              fontSize: '0.75rem',
                              fontWeight: '600',
                            }}>
                              ✓
                            </span>
                          )}
                        </h4>
                      </div>
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
              );
              };
              
              if (hasDays || hasMealIdeas || hasShoppingList) {
                return (
              <div style={{ marginTop: '2rem', paddingTop: '2rem', borderTop: '2px solid #e5e7eb' }}>
                <h2 style={{ marginBottom: '1.5rem', color: '#1f2937' }}>📋 Dietary Plan</h2>
                
                {/* Day-by-Day Meal Plan */}
                {hasDays && (
                  <div style={{ marginBottom: '2rem' }}>
                    {plan.days.map((day, dayIndex) => (
                      <div
                        key={dayIndex}
                        style={{
                          marginBottom: '2rem',
                          padding: '1.5rem',
                          background: '#f9fafb',
                          borderRadius: '12px',
                          border: '2px solid #e5e7eb',
                        }}
                      >
                        <h3 style={{ marginBottom: '1.5rem', color: '#1f2937', fontSize: '1.5rem', borderBottom: '2px solid #d1d5db', paddingBottom: '0.5rem' }}>
                          📅 Day {day.day_number}
                        </h3>
                        
                        {/* Breakfast */}
                        {day.breakfast && (
                          <div style={{ marginBottom: '1.5rem' }}>
                            <h4 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.125rem', fontWeight: '600' }}>
                              🌅 Breakfast
                            </h4>
                            {renderMeal(day.breakfast, 0, day.day_number, 'breakfast')}
                          </div>
                        )}
                        
                        {/* Lunch */}
                        {day.lunch && (
                          <div style={{ marginBottom: '1.5rem' }}>
                            <h4 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.125rem', fontWeight: '600' }}>
                              🍽️ Lunch
                            </h4>
                            {renderMeal(day.lunch, 0, day.day_number, 'lunch')}
                          </div>
                        )}
                        
                        {/* Dinner */}
                        {day.dinner && (
                          <div style={{ marginBottom: '1.5rem' }}>
                            <h4 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.125rem', fontWeight: '600' }}>
                              🌙 Dinner
                            </h4>
                            {renderMeal(day.dinner, 0, day.day_number, 'dinner')}
                          </div>
                        )}
                        
                        {/* Legacy support: main_courses (backward compatibility) */}
                        {!day.breakfast && !day.lunch && !day.dinner && day.main_courses && day.main_courses.length > 0 && (
                          <div style={{ marginBottom: '1.5rem' }}>
                            <h4 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.125rem', fontWeight: '600' }}>
                              🍽️ Main Courses
                            </h4>
                            {day.main_courses.map((meal, index) => renderMeal(meal, index, day.day_number, 'main_course'))}
                          </div>
                        )}
                        
                        {/* Small Meals */}
                        {day.small_meals && day.small_meals.length > 0 && (
                          <div style={{ marginBottom: '1.5rem' }}>
                            <h4 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.125rem', fontWeight: '600' }}>
                              🥗 Small Meals
                            </h4>
                            {day.small_meals.map((meal, index) => renderMeal(meal, index, day.day_number, 'small_meal'))}
                          </div>
                        )}
                        
                        {/* Snacks */}
                        {day.snacks && day.snacks.length > 0 && (
                          <div style={{ marginBottom: '1.5rem' }}>
                            <h4 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.125rem', fontWeight: '600' }}>
                              🍎 Snacks
                            </h4>
                            {day.snacks.map((meal, index) => renderMeal(meal, index, day.day_number, 'snack'))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Legacy Meal Ideas (backward compatibility) */}
                {!hasDays && hasMealIdeas && (
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
                      {goal.dietary_plan.total_price && (
                        <div style={{
                          marginBottom: '1.5rem',
                          padding: '1rem',
                          background: '#f0f9ff',
                          borderRadius: '6px',
                          border: '1px solid #bfdbfe',
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: '600', color: '#1e40af', fontSize: '1.125rem' }}>
                              Total Price:
                            </span>
                            <span style={{ fontWeight: '700', color: '#1e40af', fontSize: '1.25rem' }}>
                              {parseFloat(goal.dietary_plan.total_price).toFixed(2)} {goal.dietary_plan.currency}
                            </span>
                          </div>
                        </div>
                      )}
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
                                {item.offer_display_name || item.ingredient}
                              </div>
                              {item.notes && (
                                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>
                                  {item.notes}
                                </div>
                              )}
                              {(item.quantity || item.unit) && (
                                <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                  {item.quantity} {item.unit}
                                </div>
                              )}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
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
                              {item.price !== null && item.price !== undefined ? (
                                <div style={{
                                  padding: '0.5rem 1rem',
                                  background: '#f0fdf4',
                                  borderRadius: '6px',
                                  fontWeight: '600',
                                  color: '#166534',
                                  fontSize: '0.875rem',
                                  minWidth: '80px',
                                  textAlign: 'right',
                                }}>
                                  {parseFloat(item.price).toFixed(2)} {item.currency || goal.dietary_plan.currency}
                                  {item.offer_unit && item.offer_unit !== item.unit && (
                                    <div style={{ fontSize: '0.75rem', color: '#15803d', marginTop: '0.125rem' }}>
                                      / {item.offer_unit}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <div style={{
                                  padding: '0.5rem 1rem',
                                  background: '#fef3c7',
                                  borderRadius: '6px',
                                  fontWeight: '600',
                                  color: '#92400e',
                                  fontSize: '0.875rem',
                                }}>
                                  Price N/A
                                </div>
                              )}
                            </div>
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

                  </div>
                );
              } else if (plan) {
                return (
                  <div style={{
                    marginTop: '2rem',
                    padding: '2rem',
                    textAlign: 'center',
                    color: '#6b7280',
                    background: '#f9fafb',
                    borderRadius: '8px',
                    border: '1px dashed #d1d5db',
                  }}>
                    <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📝</div>
                    <p>Dietary plan exists but no meal ideas or shopping list available yet.</p>
                  </div>
                );
              } else {
                return (
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
                );
              }
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

