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

// ... existing code ...
