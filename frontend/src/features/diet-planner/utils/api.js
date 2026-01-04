/**
 * API client functions for dietary goals
 */
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from '../../../utils/api';

const API_BASE_URL = '/api/goals';

/**
 * Get available shops for a country
 * @param {string} country - Country code (e.g., 'CZ', 'SK')
 * @returns {Promise<Object>}
 */
export async function getShopsForCountry(country) {
  const token = getAccessToken();
  
  if (!token) {
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(`/api/shops/?country=${encodeURIComponent(country)}`, {
    method: 'GET',
    headers,
    credentials: 'include',
  });

  if (response.status === 401) {
    const { clearTokens } = await import('../../../utils/api');
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Create a new dietary goal
 * @param {Object} goalData
 * @param {string} goalData.prompt
 * @param {string} [goalData.dietary_restrictions]
 * @param {string} goalData.country
 * @param {string} goalData.city
 * @param {string} [goalData.language_code]
 * @param {string} [goalData.shop]
 * @returns {Promise<Object>}
 */
export async function createDietaryGoal(goalData) {
  const token = getAccessToken();
  
  if (!token) {
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    'X-CSRFToken': getCsrfToken(),
  };

  const response = await fetch(API_BASE_URL + '/', {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify(goalData),
  });

  if (response.status === 401) {
    const { clearTokens } = await import('../../../utils/api');
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Get list of user's dietary goals
 * @returns {Promise<Object>}
 */
export async function getDietaryGoalsList() {
  const token = getAccessToken();
  
  if (!token) {
    // No token - redirect to login
    console.warn('No access token found, redirecting to login');
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(API_BASE_URL + '/list/', {
    method: 'GET',
    headers,
    credentials: 'include',
  });

  if (response.status === 401) {
    // Token might be expired, try to refresh
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
          // SimpleJWT returns {"access": "..."} directly, not wrapped in "data"
          const newAccessToken = refreshData.access || refreshData.data?.access;
          if (newAccessToken) {
            setTokens(newAccessToken, refreshToken);
            // Retry original request with new token
            headers['Authorization'] = `Bearer ${newAccessToken}`;
            const retryResponse = await fetch(API_BASE_URL + '/list/', {
              method: 'GET',
              headers,
              credentials: 'include',
            });
            if (retryResponse.ok) {
              return retryResponse.json();
            }
          }
        }
      } catch (error) {
        // Refresh failed, clear tokens and redirect
        clearTokens();
        window.location.href = '/login';
        throw new Error('Session expired. Please login again.');
      }
    }
    // No refresh token or refresh failed - redirect to login
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Get details of a specific dietary goal
 * @param {number} goalId
 * @returns {Promise<Object>}
 */
export async function getDietaryGoalDetail(goalId) {
  const token = getAccessToken();
  
  if (!token) {
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(API_BASE_URL + `/${goalId}/`, {
    method: 'GET',
    headers,
    credentials: 'include',
  });

  if (response.status === 401) {
    // Token might be expired, try to refresh
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
          if (refreshData.access) {
            setTokens(refreshData.access, refreshToken);
            // Retry original request with new token
            headers['Authorization'] = `Bearer ${refreshData.access}`;
            const retryResponse = await fetch(API_BASE_URL + `/${goalId}/`, {
              method: 'GET',
              headers,
              credentials: 'include',
            });
            if (retryResponse.ok) {
              return retryResponse.json();
            }
          }
        }
      } catch (error) {
        // Refresh failed, clear tokens and redirect
        clearTokens();
        window.location.href = '/login';
        throw new Error('Session expired. Please login again.');
      }
    }
    // No refresh token or refresh failed - redirect to login
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Get CSRF token from cookies
 * @returns {string}
 */
function getCsrfToken() {
  const name = 'csrftoken';
  const cookies = document.cookie.split(';');
  for (let cookie of cookies) {
    const [key, value] = cookie.trim().split('=');
    if (key === name) {
      return decodeURIComponent(value);
    }
  }
  return '';
}

/**
 * Generate meal identifier
 * @param {number} goalId
 * @param {number} dayNumber
 * @param {string} mealType (breakfast, lunch, dinner, small_meal, snack)
 * @param {number} mealIndex
 * @returns {string}
 */
export function generateMealIdentifier(goalId, dayNumber, mealType, mealIndex = 0) {
  return `${goalId}:${dayNumber}:${mealType}:${mealIndex}`;
}

/**
 * Get recipe by meal identifier
 * @param {string} mealIdentifier
 * @returns {Promise<Object>}
 */
export async function getRecipe(mealIdentifier) {
  const token = getAccessToken();
  
  if (!token) {
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(`/api/recipes/${encodeURIComponent(mealIdentifier)}/`, {
    method: 'GET',
    headers,
    credentials: 'include',
  });

  if (response.status === 401) {
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Get all meal instances for a dietary goal
 * @param {number} goalId
 * @returns {Promise<Object>} Response with data array of meal instances
 */
export async function getMealInstancesForGoal(goalId) {
  const token = getAccessToken();
  
  if (!token) {
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(`/api/goals/${goalId}/meal-instances/`, {
    method: 'GET',
    headers,
    credentials: 'include',
  });

  if (response.status === 401) {
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${response.status}: Failed to fetch meal instances`);
  }

  const data = await response.json();
  if (data.status === 'success') {
    return data;
  } else {
    throw new Error(data.error || 'Failed to fetch meal instances');
  }
}

/**
 * Get meal instance by meal identifier
 * @param {string} mealIdentifier
 * @returns {Promise<Object>}
 */
export async function getMealInstance(mealIdentifier) {
  const token = getAccessToken();
  
  if (!token) {
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(`/api/meals/${encodeURIComponent(mealIdentifier)}/`, {
    method: 'GET',
    headers,
    credentials: 'include',
  });

  if (response.status === 401) {
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (response.status === 404) {
    // Meal instance doesn't exist yet, return null
    return null;
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Mark meal as cooked or uncooked
 * @param {string} mealIdentifier
 * @param {Object} mealData
 * @param {number} mealData.goal_id
 * @param {string} mealData.meal_name
 * @param {number} mealData.day_number
 * @param {string} mealData.meal_type
 * @param {boolean} mealData.is_cooked
 * @param {string} [mealData.notes]
 * @returns {Promise<Object>}
 */
export async function markMealAsCooked(mealIdentifier, mealData) {
  const token = getAccessToken();
  
  if (!token) {
    window.location.href = '/login';
    throw new Error('Not authenticated. Please login.');
  }
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(`/api/meals/${encodeURIComponent(mealIdentifier)}/`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify(mealData),
  });

  if (response.status === 401) {
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}
