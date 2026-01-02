/**
 * API client functions for dietary goals
 */
import { getAccessToken } from '../../../utils/api';

const API_BASE_URL = '/api/goals';

/**
 * Create a new dietary goal
 * @param {Object} goalData
 * @param {string} goalData.prompt
 * @param {string} [goalData.dietary_restrictions]
 * @param {string} goalData.country
 * @param {string} goalData.city
 * @param {string} [goalData.language_code]
 * @returns {Promise<Object>}
 */
export async function createDietaryGoal(goalData) {
  const token = getAccessToken();
  const headers = {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken(),
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(API_BASE_URL + '/', {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify(goalData),
  });

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
  const headers = {
    'Content-Type': 'application/json',
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(API_BASE_URL + '/list/', {
    method: 'GET',
    headers,
    credentials: 'include',
  });

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
  const headers = {
    'Content-Type': 'application/json',
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(API_BASE_URL + `/${goalId}/`, {
    method: 'GET',
    headers,
    credentials: 'include',
  });

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

