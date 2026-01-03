import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from '../utils/api';
import { getRecipe, getMealInstance, markMealAsCooked, generateMealIdentifier } from '../features/diet-planner/utils/api';
import { Navigation } from '../components/Navigation';

/**
 * Page for viewing a recipe and marking it as cooked
 */
export function RecipePage() {
  const navigate = useNavigate();
  const { mealIdentifier } = useParams();
  const [recipe, setRecipe] = useState(null);
  const [mealInstance, setMealInstance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isMarkingCooked, setIsMarkingCooked] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const { getAccessToken, getRefreshToken, setTokens, clearTokens } = await import('../utils/api');
        let token = getAccessToken();
        let headers = {
          'Content-Type': 'application/json',
        };
        
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        // Fetch recipe
        let recipeResponse = await fetch(`/api/recipes/${encodeURIComponent(mealIdentifier)}/`, {
          headers,
          credentials: 'include',
        });
        
        // Handle 401 - token expired, try to refresh
        if (recipeResponse.status === 401) {
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
                  headers['Authorization'] = `Bearer ${newAccessToken}`;
                  recipeResponse = await fetch(`/api/recipes/${encodeURIComponent(mealIdentifier)}/`, {
                    headers,
                    credentials: 'include',
                  });
                }
              }
            } catch (refreshError) {
              clearTokens();
              window.location.href = '/login';
              return;
            }
          } else {
            clearTokens();
            window.location.href = '/login';
            return;
          }
        }
        
        if (recipeResponse.status === 404) {
          setError('Recipe not found');
          setLoading(false);
          return;
        }
        
        if (!recipeResponse.ok) {
          const errorData = await recipeResponse.json().catch(() => ({}));
          throw new Error(errorData.error || 'Failed to load recipe');
        }
        
        const recipeData = await recipeResponse.json();
        if (recipeData.status === 'success') {
          setRecipe(recipeData.data);
        } else {
          throw new Error(recipeData.error || 'Failed to load recipe');
        }

        // Fetch meal instance
        try {
          const mealInstanceData = await getMealInstance(mealIdentifier);
          if (mealInstanceData && mealInstanceData.status === 'success') {
            setMealInstance(mealInstanceData.data);
          }
        } catch (err) {
          // Meal instance doesn't exist yet, that's okay
          console.log('Meal instance not found, will be created when marked as cooked');
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (mealIdentifier) {
      fetchData();
    }
  }, [mealIdentifier]);

  const handleMarkAsCooked = async () => {
    if (!recipe) return;
    
    setIsMarkingCooked(true);
    try {
      const isCurrentlyCooked = mealInstance?.is_cooked || false;
      const mealData = {
        goal_id: recipe.dietary_goal_id,
        meal_name: recipe.name,
        day_number: parseInt(mealIdentifier.split(':')[1]),
        meal_type: mealIdentifier.split(':')[2],
        is_cooked: !isCurrentlyCooked,
        notes: mealInstance?.notes || '',
      };

      const response = await markMealAsCooked(mealIdentifier, mealData);
      if (response.status === 'success') {
        setMealInstance(response.data);
      } else {
        throw new Error(response.error || 'Failed to update meal status');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsMarkingCooked(false);
    }
  };

  if (loading) {
    return (
      <div className="App">
        <Navigation />
        <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
          <div style={{ textAlign: 'center', padding: '4rem' }}>
            <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⏳</div>
            <p style={{ color: '#6b7280' }}>Loading recipe...</p>
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
          <button
            onClick={() => navigate(-1)}
            className="btn btn-secondary"
          >
            ← Go Back
          </button>
        </div>
      </div>
    );
  }

  if (!recipe) {
    return (
      <div className="App">
        <Navigation />
        <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
          <div style={{ textAlign: 'center', padding: '4rem' }}>
            <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>📝</div>
            <p style={{ color: '#6b7280' }}>Recipe not found</p>
            <button
              onClick={() => navigate(-1)}
              className="btn btn-secondary"
              style={{ marginTop: '1rem' }}
            >
              ← Go Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  const isCooked = mealInstance?.is_cooked || false;

  return (
    <div className="App">
      <Navigation />
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        <div style={{
          background: 'white',
          padding: '2rem',
          borderRadius: '12px',
          boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
        }}>
          {/* Header */}
          <div style={{ marginBottom: '2rem', paddingBottom: '1.5rem', borderBottom: '2px solid #e5e7eb' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
              <h1 style={{ margin: 0, fontSize: '2rem', color: '#1f2937' }}>{recipe.name}</h1>
              {isCooked && (
                <span style={{
                  padding: '0.5rem 1rem',
                  background: '#d1fae5',
                  color: '#065f46',
                  borderRadius: '9999px',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  border: '1px solid #10b981',
                }}>
                  ✓ Cooked
                </span>
              )}
            </div>
            <button
              onClick={() => navigate(-1)}
              className="btn btn-secondary"
              style={{ marginTop: '0.5rem' }}
            >
              ← Back
            </button>
          </div>

          {/* Description */}
          {recipe.description && (
            <div style={{ marginBottom: '2rem' }}>
              <p style={{ color: '#6b7280', fontSize: '1rem', lineHeight: '1.6' }}>
                {recipe.description}
              </p>
            </div>
          )}

          {/* Time and Servings Info */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '1rem',
            marginBottom: '2rem',
            padding: '1rem',
            background: '#f9fafb',
            borderRadius: '8px',
          }}>
            {recipe.preparation_time && (
              <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Preparation</div>
                <div style={{ fontWeight: '600', color: '#1f2937' }}>⏱️ {recipe.preparation_time} min</div>
              </div>
            )}
            {recipe.cooking_time && (
              <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Cooking</div>
                <div style={{ fontWeight: '600', color: '#1f2937' }}>🔥 {recipe.cooking_time} min</div>
              </div>
            )}
            {recipe.servings && (
              <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Servings</div>
                <div style={{ fontWeight: '600', color: '#1f2937' }}>🍽️ {recipe.servings}</div>
              </div>
            )}
          </div>

          {/* Ingredients */}
          {recipe.ingredients && recipe.ingredients.length > 0 && (
            <div style={{ marginBottom: '2rem' }}>
              <h2 style={{ marginBottom: '1rem', color: '#1f2937', fontSize: '1.5rem' }}>Ingredients</h2>
              <div style={{
                padding: '1.5rem',
                background: '#f9fafb',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
              }}>
                <ul style={{ margin: 0, paddingLeft: '1.5rem', listStyle: 'none' }}>
                  {recipe.ingredients.map((ingredient, i) => (
                    <li key={i} style={{
                      marginBottom: '0.75rem',
                      paddingLeft: '1.5rem',
                      position: 'relative',
                      color: '#374151',
                    }}>
                      <span style={{
                        position: 'absolute',
                        left: 0,
                        color: '#10b981',
                        fontWeight: 'bold',
                      }}>•</span>
                      {ingredient}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Instructions */}
          {recipe.instructions && recipe.instructions.length > 0 && (
            <div style={{ marginBottom: '2rem' }}>
              <h2 style={{ marginBottom: '1rem', color: '#1f2937', fontSize: '1.5rem' }}>Instructions</h2>
              <div style={{
                padding: '1.5rem',
                background: '#f9fafb',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
              }}>
                <ol style={{ margin: 0, paddingLeft: '1.5rem' }}>
                  {recipe.instructions.map((instruction, i) => (
                    <li key={i} style={{
                      marginBottom: '1rem',
                      color: '#374151',
                      lineHeight: '1.6',
                    }}>
                      {instruction}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          )}

          {/* Nutritional Info */}
          {recipe.nutritional_info && Object.keys(recipe.nutritional_info).length > 0 && (
            <div style={{ marginBottom: '2rem' }}>
              <h2 style={{ marginBottom: '1rem', color: '#1f2937', fontSize: '1.5rem' }}>Nutritional Information</h2>
              <div style={{
                padding: '1.5rem',
                background: '#f9fafb',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
                display: 'flex',
                gap: '2rem',
                flexWrap: 'wrap',
              }}>
                {recipe.nutritional_info.calories && (
                  <div>
                    <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Calories</div>
                    <div style={{ fontWeight: '600', color: '#1f2937' }}>🔥 {recipe.nutritional_info.calories}</div>
                  </div>
                )}
                {recipe.nutritional_info.protein && (
                  <div>
                    <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Protein</div>
                    <div style={{ fontWeight: '600', color: '#1f2937' }}>💪 {recipe.nutritional_info.protein}</div>
                  </div>
                )}
                {recipe.nutritional_info.carbs && (
                  <div>
                    <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Carbs</div>
                    <div style={{ fontWeight: '600', color: '#1f2937' }}>🍞 {recipe.nutritional_info.carbs}</div>
                  </div>
                )}
                {recipe.nutritional_info.fat && (
                  <div>
                    <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Fat</div>
                    <div style={{ fontWeight: '600', color: '#1f2937' }}>🥑 {recipe.nutritional_info.fat}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Mark as Cooked Button */}
          <div style={{
            marginTop: '2rem',
            paddingTop: '2rem',
            borderTop: '2px solid #e5e7eb',
            display: 'flex',
            gap: '1rem',
            alignItems: 'center',
          }}>
            <button
              onClick={handleMarkAsCooked}
              disabled={isMarkingCooked}
              className={isCooked ? "btn btn-secondary" : "btn btn-primary"}
              style={{ minWidth: '200px' }}
            >
              {isMarkingCooked ? 'Updating...' : isCooked ? '✓ Mark as Not Cooked' : '✓ Mark as Cooked'}
            </button>
            {mealInstance?.cooked_at && (
              <span style={{ color: '#6b7280', fontSize: '0.875rem' }}>
                Cooked on {new Date(mealInstance.cooked_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

