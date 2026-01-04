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
  const [expandedDays, setExpandedDays] = useState(new Set()); // Track which days are expanded

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

  // Fetch cooked meals
  useEffect(() => {
    const fetchCookedMeals = async () => {
      if (!goal || !goal.dietary_plan) return;
      
      try {
        const plan = goal.dietary_plan;
        const mealIdentifiers = [];
        
        // Collect all meal identifiers
        if (plan.days && Array.isArray(plan.days)) {
          plan.days.forEach((day) => {
            if (day.breakfast) {
              mealIdentifiers.push(generateMealIdentifier(goal.id, day.day_number, 'breakfast', 0));
            }
            if (day.lunch) {
              mealIdentifiers.push(generateMealIdentifier(goal.id, day.day_number, 'lunch', 0));
            }
            if (day.dinner) {
              mealIdentifiers.push(generateMealIdentifier(goal.id, day.day_number, 'dinner', 0));
            }
            if (day.small_meals && Array.isArray(day.small_meals)) {
              day.small_meals.forEach((_, index) => {
                mealIdentifiers.push(generateMealIdentifier(goal.id, day.day_number, 'small_meal', index));
              });
            }
            if (day.snacks && Array.isArray(day.snacks)) {
              day.snacks.forEach((_, index) => {
                mealIdentifiers.push(generateMealIdentifier(goal.id, day.day_number, 'snack', index));
              });
            }
          });
        }
        
        // Fetch cooked status for each meal
        const cookedStatus = {};
        await Promise.all(
          mealIdentifiers.map(async (identifier) => {
            try {
              const mealInstance = await getMealInstance(identifier);
              if (mealInstance && mealInstance.data && mealInstance.data.is_cooked) {
                cookedStatus[identifier] = true;
              }
            } catch (err) {
              // Meal instance doesn't exist yet, that's fine
            }
          })
        );
        
        setCookedMeals(cookedStatus);
      } catch (err) {
        console.error('Error fetching cooked meals:', err);
      }
    };

    if (goal) {
      fetchCookedMeals();
    }
  }, [goal]);

  const toggleDay = (dayNumber) => {
    setExpandedDays(prev => {
      const newSet = new Set(prev);
      if (newSet.has(dayNumber)) {
        newSet.delete(dayNumber);
      } else {
        newSet.add(dayNumber);
      }
      return newSet;
    });
  };

  // Helper function to render meal summary (collapsed view)
  const renderMealSummary = (meal, dayNumber, mealType, index) => {
    if (!meal) return null;
    
    const mealIdentifier = generateMealIdentifier(goal.id, dayNumber, mealType, index);
    const isCooked = cookedMeals[mealIdentifier] || false;
    
    return (
      <div
        key={`${mealType}-${index}`}
        onClick={(e) => {
          e.stopPropagation();
          navigate(`/recipe/${encodeURIComponent(mealIdentifier)}`);
        }}
        style={{
          padding: '0.75rem',
          background: isCooked ? '#f0fdf4' : 'white',
          borderRadius: '6px',
          border: isCooked ? '1px solid #10b981' : '1px solid #e5e7eb',
          marginBottom: '0.5rem',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <span style={{ fontWeight: '600', color: '#1f2937', fontSize: '0.9rem' }}>
              {meal.name}
            </span>
            {isCooked && (
              <span style={{
                padding: '0.125rem 0.375rem',
                background: '#10b981',
                color: 'white',
                borderRadius: '9999px',
                fontSize: '0.7rem',
                fontWeight: '600',
              }}>
                ✓
              </span>
            )}
          </div>
          {meal.nutritional_info && (
            <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem', color: '#6b7280', flexWrap: 'wrap' }}>
              {meal.nutritional_info.calories && (
                <span>🔥 {meal.nutritional_info.calories} cal</span>
              )}
              {meal.nutritional_info.protein && (
                <span>💪 {meal.nutritional_info.protein}</span>
              )}
              {meal.nutritional_info.carbs && (
                <span>🍞 {meal.nutritional_info.carbs}</span>
              )}
              {meal.nutritional_info.fat && (
                <span>🥑 {meal.nutritional_info.fat}</span>
              )}
            </div>
          )}
        </div>
        {meal.preparation_time && (
          <span style={{
            padding: '0.25rem 0.5rem',
            background: '#dbeafe',
            color: '#1e40af',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            fontWeight: '500',
            marginLeft: '0.5rem',
          }}>
            ⏱️ {meal.preparation_time} min
          </span>
        )}
      </div>
    );
  };

  // Helper function to render a meal (expanded view)
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

  if (loading) {
    return (
      <div className="App">
        <Navigation />
        <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
          <div style={{ textAlign: 'center', padding: '4rem 2rem' }}>
            <p>Loading goal details...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="App">
        <Navigation />
        <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
          <div style={{
            padding: '2rem',
            background: '#fee2e2',
            border: '1px solid #fca5a5',
            borderRadius: '8px',
            color: '#991b1b',
          }}>
            <h2 style={{ marginTop: 0 }}>Error</h2>
            <p>{error}</p>
            <button
              onClick={() => navigate('/goals')}
              className="btn btn-primary"
              style={{ marginTop: '1rem' }}
            >
              Back to Goals
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!goal) {
    return (
      <div className="App">
        <Navigation />
        <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
          <div style={{ textAlign: 'center', padding: '4rem 2rem' }}>
            <p>Goal not found</p>
            <button
              onClick={() => navigate('/goals')}
              className="btn btn-primary"
              style={{ marginTop: '1rem' }}
            >
              Back to Goals
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="App">
      <Navigation />
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        <div style={{ marginBottom: '2rem' }}>
          <button
            onClick={() => navigate('/goals')}
            className="btn btn-secondary"
            style={{ marginBottom: '1rem' }}
          >
            ← Back to Goals
          </button>
          <h1 style={{ margin: 0, fontSize: '2rem', color: '#1f2937' }}>Goal #{goal.id}</h1>
          <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <span style={{
              padding: '0.5rem 1rem',
              background: goal.status === 'completed' ? '#d1fae5' : goal.status === 'processing' ? '#fef3c7' : goal.status === 'failed' ? '#fee2e2' : '#e5e7eb',
              color: goal.status === 'completed' ? '#065f46' : goal.status === 'processing' ? '#92400e' : goal.status === 'failed' ? '#991b1b' : '#374151',
              borderRadius: '9999px',
              fontSize: '0.875rem',
              fontWeight: '600',
            }}>
              {goal.status}
            </span>
            <span style={{ padding: '0.5rem 1rem', color: '#6b7280', fontSize: '0.875rem' }}>
              📍 {goal.city}, {goal.country}
            </span>
            {goal.shop && (
              <span style={{ padding: '0.5rem 1rem', color: '#6b7280', fontSize: '0.875rem' }}>
                🛒 {goal.shop}
              </span>
            )}
          </div>
        </div>

            {/* Dietary Plan */}
            {(() => {
              const plan = goal.dietary_plan;
              const hasDays = plan?.days && Array.isArray(plan.days) && plan.days.length > 0;
              const hasMealIdeas = plan?.meal_ideas && Array.isArray(plan.meal_ideas) && plan.meal_ideas.length > 0; // Legacy support
              const hasShoppingList = plan?.shopping_list && Array.isArray(plan.shopping_list) && plan.shopping_list.length > 0;
              
              if (hasDays || hasMealIdeas || hasShoppingList) {
                return (
              <div style={{ marginTop: '2rem', paddingTop: '2rem', borderTop: '2px solid #e5e7eb' }}>
                <h2 style={{ marginBottom: '1.5rem', color: '#1f2937' }}>📋 Dietary Plan</h2>
                
                {/* Shopping List - moved to top */}
                {hasShoppingList && (
                  <div style={{ marginBottom: '2rem' }}>
                    <h3 style={{ marginBottom: '1rem', color: '#374151', fontSize: '1.25rem' }}>🛒 Shopping List</h3>
                    <div style={{
                      padding: '1.5rem',
                      background: '#f9fafb',
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                    }}>
                      {plan.total_price && (
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
                              {parseFloat(plan.total_price).toFixed(2)} {plan.currency}
                            </span>
                          </div>
                        </div>
                      )}
                      <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {plan.shopping_list.map((item, index) => (
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
                                  {parseFloat(item.price).toFixed(2)} {item.currency || plan.currency}
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

                {/* Day-by-Day Meal Plan with Accordion */}
                {hasDays && (
                  <div style={{ marginBottom: '2rem' }}>
                    {plan.days.map((day, dayIndex) => {
                      const isExpanded = expandedDays.has(day.day_number);
                      const meals = [
                        day.breakfast && { meal: day.breakfast, type: 'breakfast', label: '🌅 Breakfast', index: 0 },
                        day.lunch && { meal: day.lunch, type: 'lunch', label: '🍽️ Lunch', index: 0 },
                        day.dinner && { meal: day.dinner, type: 'dinner', label: '🌙 Dinner', index: 0 },
                        ...(day.small_meals || []).map((meal, idx) => ({ meal, type: 'small_meal', label: '🥗 Small Meal', index: idx })),
                        ...(day.snacks || []).map((meal, idx) => ({ meal, type: 'snack', label: '🍎 Snack', index: idx })),
                      ].filter(Boolean);

                      return (
                        <div
                          key={dayIndex}
                          style={{
                            marginBottom: '1rem',
                            background: '#f9fafb',
                            borderRadius: '12px',
                            border: '2px solid #e5e7eb',
                            overflow: 'hidden',
                          }}
                        >
                          {/* Accordion Header */}
                          <div
                            onClick={() => toggleDay(day.day_number)}
                            style={{
                              padding: '1rem 1.5rem',
                              cursor: 'pointer',
                              background: isExpanded ? '#f3f4f6' : '#f9fafb',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              transition: 'background 0.2s',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background = '#f3f4f6';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = isExpanded ? '#f3f4f6' : '#f9fafb';
                            }}
                          >
                            <h3 style={{ margin: 0, color: '#1f2937', fontSize: '1.25rem', fontWeight: '600' }}>
                              📅 Day {day.day_number}
                            </h3>
                            <span style={{ fontSize: '1.25rem', color: '#6b7280' }}>
                              {isExpanded ? '▼' : '▶'}
                            </span>
                          </div>

                          {/* Accordion Content */}
                          {isExpanded ? (
                            <div style={{ padding: '1.5rem' }}>
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
                          ) : (
                            <div style={{ padding: '1rem 1.5rem', background: 'white' }}>
                              {meals.map(({ meal, type, index }) => 
                                renderMealSummary(meal, day.day_number, type, index)
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
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
                          <h4 style={{ margin: '0 0 0.5rem 0', color: '#1f2937' }}>{meal.name}</h4>
                          {meal.description && (
                            <p style={{ margin: '0 0 0.5rem 0', color: '#6b7280' }}>{meal.description}</p>
                          )}
                          {meal.ingredients && (
                            <div style={{ fontSize: '0.875rem', color: '#4b5563' }}>
                              <strong>Ingredients:</strong> {meal.ingredients.join(', ')}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
            }
              
              return (
                <div style={{ marginTop: '2rem', paddingTop: '2rem', borderTop: '2px solid #e5e7eb' }}>
                  <p>Dietary plan exists but no meal ideas or shopping list available yet.</p>
                </div>
              );
            })()}
      </div>
    </div>
  );
}
