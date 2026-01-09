import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getAccessToken } from '../utils/api';
import { Navigation } from '../components/Navigation';
import { generateMealIdentifier, getMealInstancesForGoal, markMealAsCooked, getRecipe } from '../features/diet-planner/utils/api';

/**
 * Page for viewing details of a specific dietary goal.
 *
 * Displays:
 * - Goal metadata (status, location, shop)
 * - Shopping list with quantities and prices
 * - Day-by-day meal plan with accordion navigation
 *
 * Shopping List Data Structure (from backend):
 * {
 *   ingredient: string,      // Ingredient name
 *   quantity: number,        // Required quantity
 *   unit: string,           // Unit (g, kg, ml, l, ks)
 *   price: number | null,   // Calculated price (may be null if not found)
 *   currency: string,       // Currency code (CZK, EUR, etc.)
 *   matched_product_name: string,  // Name of matched shop product
 *   price_source: string,   // 'backend_package_logic' | 'llm_estimation_service' | 'not_found'
 *   validation_note: string // If quantity was adjusted
 * }
 */

/**
 * Safely parse a price value to a displayable string.
 * Handles null, undefined, NaN, and invalid values gracefully.
 *
 * @param {any} price - Price value to parse
 * @returns {string | null} - Formatted price string or null if invalid
 */
const safeParsePrice = (price) => {
  if (price === null || price === undefined) {
    return null;
  }
  const parsed = parseFloat(price);
  if (isNaN(parsed) || !isFinite(parsed)) {
    return null;
  }
  return parsed.toFixed(2);
};

/**
 * Format quantity with unit for display.
 * Handles edge cases like missing values.
 *
 * @param {number} quantity - Quantity value
 * @param {string} unit - Unit string
 * @returns {string} - Formatted quantity string
 */
const formatQuantity = (quantity, unit) => {
  if (!quantity && quantity !== 0) return '';
  const qty = typeof quantity === 'number' ? quantity : parseFloat(quantity);
  if (isNaN(qty)) return '';
  // Round to 2 decimal places if needed
  const displayQty = Number.isInteger(qty) ? qty : qty.toFixed(2);
  return unit ? `${displayQty} ${unit}` : `${displayQty}`;
};

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
        console.log('GoalDetailPage: Fetching goal for goalId:', goalId);
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
        console.log('GoalDetailPage: Goal data received:', data);
        if (data.status === 'success') {
          console.log('GoalDetailPage: Setting goal:', data.data);
          setGoal(data.data);
        } else {
          throw new Error(data.error || 'Failed to load goal');
        }
      } catch (err) {
        console.error('GoalDetailPage: Error loading goal:', err);
        console.error('GoalDetailPage: Error stack:', err.stack);
        setError(err.message || 'Failed to load goal');
        setLoading(false);
      }
    };

    if (goalId) {
      fetchGoal();
    } else {
      console.warn('GoalDetailPage: No goalId provided');
      setError('No goal ID provided');
      setLoading(false);
    }
  }, [goalId]);

  // Fetch cooked meals using batch endpoint
  useEffect(() => {
    const fetchCookedMeals = async () => {
      if (!goal) return;
      
      try {
        const response = await getMealInstancesForGoal(goal.id);
        if (response.status === 'success' && response.data) {
          // Map meal instances to cookedStatus object by meal_identifier
          const cookedStatus = {};
          response.data.forEach((mealInstance) => {
            if (mealInstance.is_cooked) {
              cookedStatus[mealInstance.meal_identifier] = true;
            }
          });
          setCookedMeals(cookedStatus);
        }
      } catch (err) {
        console.error('Error fetching cooked meals:', err);
        // Set empty object on error - meals will show as not cooked
        setCookedMeals({});
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

  const handleMarkAsCooked = async (mealIdentifier, meal, dayNumber, mealType, index) => {
    try {
      // Get recipe to get dietary_goal_id
      const recipeResponse = await getRecipe(mealIdentifier);
      if (recipeResponse.status !== 'success') {
        throw new Error('Failed to fetch recipe');
      }
      const recipe = recipeResponse.data;

      const isCurrentlyCooked = cookedMeals[mealIdentifier] || false;
      const mealData = {
        goal_id: recipe.dietary_goal_id,
        meal_name: meal.name,
        day_number: dayNumber,
        meal_type: mealType,
        is_cooked: !isCurrentlyCooked,
        notes: '',
      };

      const response = await markMealAsCooked(mealIdentifier, mealData);
      if (response.status === 'success') {
        // Update local state
        setCookedMeals(prev => ({
          ...prev,
          [mealIdentifier]: !isCurrentlyCooked,
        }));
      } else {
        throw new Error(response.error || 'Failed to update meal status');
      }
    } catch (err) {
      console.error('Error marking meal as cooked:', err);
      alert(err.message || 'Failed to update meal status');
    }
  };

  // Helper function to render meal summary (collapsed view)
  const renderMealSummary = (meal, dayNumber, mealType, index) => {
    if (!meal) return null;
    
    const mealIdentifier = generateMealIdentifier(goal.id, dayNumber, mealType, index);
    const isCooked = cookedMeals[mealIdentifier] || false;
    
    return (
      <div
        key={`${mealType}-${index}`}
        style={{
          padding: '0.75rem',
          background: isCooked ? '#f0fdf4' : 'white',
          borderRadius: '6px',
          border: isCooked ? '1px solid #10b981' : '1px solid #e5e7eb',
          marginBottom: '0.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div 
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/recipe/${encodeURIComponent(mealIdentifier)}`);
          }}
          style={{ flex: 1, cursor: 'pointer' }}
        >
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {meal.preparation_time && (
            <span style={{
              padding: '0.25rem 0.5rem',
              background: '#dbeafe',
              color: '#1e40af',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: '500',
            }}>
              ⏱️ {meal.preparation_time} min
            </span>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleMarkAsCooked(mealIdentifier, meal, dayNumber, mealType, index);
            }}
            style={{
              padding: '0.375rem 0.75rem',
              background: isCooked ? '#f3f4f6' : '#10b981',
              color: isCooked ? '#374151' : 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.75rem',
              fontWeight: '600',
              cursor: 'pointer',
            }}
          >
            {isCooked ? '✗' : '✓'}
          </button>
        </div>
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
                        {meal.ingredients.map((ingredient, i) => {
                          // Handle both object format {name, quantity, unit} and string format
                          let ingredientText = ingredient;
                          if (typeof ingredient === 'object' && ingredient !== null) {
                            const quantity = ingredient.quantity || '';
                            const unit = ingredient.unit || '';
                            const name = ingredient.name || '';
                            ingredientText = quantity && unit 
                              ? `${quantity} ${unit} ${name}`.trim()
                              : name || JSON.stringify(ingredient);
                          }
                          
                          return (
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
                              {ingredientText}
                            </span>
                          );
                        })}
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

  // Add error boundary check
  if (error && !loading) {
    console.error('GoalDetailPage: Rendering error state:', error);
  }

  return (
    <div className="App">
      <Navigation />
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem', minHeight: '400px' }}>
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
              // Try both snake_case and camelCase (Django might serialize differently)
              const shoppingListData = plan?.shopping_list || plan?.shoppingList;
              const hasShoppingList = shoppingListData && Array.isArray(shoppingListData) && shoppingListData.length > 0;
              
              // Debug logging
              console.log('Dietary Plan Debug:', {
                plan,
                hasShoppingList,
                shoppingList: plan?.shopping_list,
                shoppingListLength: plan?.shopping_list?.length,
                hasDays,
                hasMealIdeas,
              });
              
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
                      {/* Total price summary */}
                      {(() => {
                        const totalPrice = safeParsePrice(plan.total_price);
                        if (!totalPrice) return null;

                        return (
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
                                {totalPrice} {plan.currency || ''}
                              </span>
                            </div>
                            {/* Show item count for transparency */}
                            <div style={{ fontSize: '0.75rem', color: '#3b82f6', marginTop: '0.5rem' }}>
                              {(plan?.shopping_list || plan?.shoppingList || []).length} items
                              {' | '}
                              {(plan?.shopping_list || plan?.shoppingList || []).filter(i => safeParsePrice(i.price) !== null).length} priced
                            </div>
                          </div>
                        );
                      })()}
                      <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {(plan?.shopping_list || plan?.shoppingList || []).map((item, index) => {
                          const priceDisplay = safeParsePrice(item.price);
                          const quantityDisplay = formatQuantity(item.quantity, item.unit);
                          const isEstimated = item.price_source === 'llm_estimation_service' || item.estimated;

                          return (
                            <div
                              key={item.ingredient ? `${item.ingredient}-${index}` : index}
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
                              {/* Left side: Item name and details */}
                              <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: '600', color: '#1f2937', marginBottom: '0.25rem' }}>
                                  {item.matched_product_name || item.offer_display_name || item.ingredient || 'Unknown item'}
                                </div>
                                {/* Show original ingredient name if matched to different product */}
                                {item.matched_product_name && item.ingredient && item.matched_product_name !== item.ingredient && (
                                  <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginBottom: '0.25rem' }}>
                                    ({item.ingredient})
                                  </div>
                                )}
                                {item.notes && (
                                  <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>
                                    {item.notes}
                                  </div>
                                )}
                                {/* Show validation note if quantity was adjusted */}
                                {item.validation_note && (
                                  <div style={{ fontSize: '0.75rem', color: '#f59e0b', marginBottom: '0.25rem' }}>
                                    {item.validation_note}
                                  </div>
                                )}
                              </div>

                              {/* Right side: Quantity badge and price */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                {/* Quantity badge */}
                                {quantityDisplay && (
                                  <div style={{
                                    padding: '0.5rem 1rem',
                                    background: '#eff6ff',
                                    borderRadius: '6px',
                                    fontWeight: '600',
                                    color: '#1e40af',
                                    fontSize: '0.875rem',
                                    whiteSpace: 'nowrap',
                                  }}>
                                    {quantityDisplay}
                                  </div>
                                )}

                                {/* Price badge */}
                                {priceDisplay !== null ? (
                                  <div style={{
                                    padding: '0.5rem 1rem',
                                    background: isEstimated ? '#fef3c7' : '#f0fdf4',
                                    borderRadius: '6px',
                                    fontWeight: '600',
                                    color: isEstimated ? '#92400e' : '#166534',
                                    fontSize: '0.875rem',
                                    minWidth: '80px',
                                    textAlign: 'right',
                                  }}>
                                    {priceDisplay} {item.currency || plan.currency || ''}
                                    {isEstimated && (
                                      <div style={{ fontSize: '0.65rem', color: '#b45309', marginTop: '0.125rem' }}>
                                        (estimated)
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <div style={{
                                    padding: '0.5rem 1rem',
                                    background: '#fee2e2',
                                    borderRadius: '6px',
                                    fontWeight: '600',
                                    color: '#991b1b',
                                    fontSize: '0.875rem',
                                  }}>
                                    Price N/A
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
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
