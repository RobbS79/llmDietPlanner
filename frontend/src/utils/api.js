/**
 * API utility for making requests to the backend.
 * Handles JWT token storage, authentication headers, and safe response parsing.
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

/**
 * Token and User Management
 */
export const getAccessToken = () => localStorage.getItem('access_token');
export const getRefreshToken = () => localStorage.getItem('refresh_token');
export const getUser = () => {
  const userStr = localStorage.getItem('user');
  return userStr ? JSON.parse(userStr) : null;
};

export const setTokens = (accessToken, refreshToken) => {
  if (accessToken) localStorage.setItem('access_token', accessToken);
  if (refreshToken) localStorage.setItem('refresh_token', refreshToken);
};

export const setUser = (user) => {
  localStorage.setItem('user', JSON.stringify(user));
};

export const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
};

/**
 * Helper to safely parse JSON from a response.
 */
const safeJson = async (response) => {
  try {
    return await response.json();
  } catch (err) {
    return null; 
  }
};

/**
 * Make an authenticated API request with automatic token refresh logic
 */
export const apiRequest = async (endpoint, options = {}) => {
  const token = getAccessToken();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      const refreshToken = getRefreshToken();
      if (refreshToken) {
        try {
          const refreshResponse = await fetch(`${API_BASE_URL}/auth/refresh/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh: refreshToken }),
          });

          if (refreshResponse.ok) {
            const data = await refreshResponse.json();
            setTokens(data.access, data.refresh || refreshToken);
            
            // Retry original request
            headers['Authorization'] = `Bearer ${data.access}`;
            return fetch(`${API_BASE_URL}${endpoint}`, {
              ...options,
              headers,
            });
          }
        } catch (error) {
          clearTokens();
          window.location.href = '/login';
          throw new Error('Session expired. Please login again.');
        }
      }
    }

    return response;
  } catch (error) {
    console.error('API Request Error:', error);
    throw error;
  }
};

/**
 * Authentication API functions
 */
export const authAPI = {
  register: async (username, email, password, passwordConfirm) => {
    const response = await fetch(`${API_BASE_URL}/auth/register/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password, passwordConfirm }),
    });
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || data?.detail || 'Registration failed');
    return data;
  },

  login: async (username, password) => {
    const response = await fetch(`${API_BASE_URL}/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || data?.detail || 'Login failed');

    const payload = data?.data || data;
    if (payload.access) {
      setTokens(payload.access, payload.refresh);
      if (payload.user) setUser(payload.user);
    }
    return data;
  },

  googleLogin: async (accessToken) => {
    const response = await fetch(`${API_BASE_URL}/auth/google/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: accessToken }),
    });
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || 'Google login failed');

    const payload = data?.data || data;
    if (payload.access) {
      setTokens(payload.access, payload.refresh);
      if (payload.user) setUser(payload.user);
    }
    return data;
  },

  facebookLogin: async (accessToken) => {
    const response = await fetch(`${API_BASE_URL}/auth/facebook/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: accessToken }),
    });
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || 'Facebook login failed');

    const payload = data?.data || data;
    if (payload.access) {
      setTokens(payload.access, payload.refresh);
      if (payload.user) setUser(payload.user);
    }
    return data;
  },

  verifyEmail: async (uid, token) => {
    const response = await fetch(`${API_BASE_URL}/auth/verify-email/?uid=${uid}&token=${token}`);
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || 'Email verification failed');
    return data;
  },

  getProfile: async () => {
    const response = await apiRequest('/auth/profile/');
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || 'Failed to get profile');
    return data;
  },

  logout: () => clearTokens(),
};

/**
 * Shopify API functions
 */
export const shopifyAPI = {
  createCheckout: async (variantIds, quantities, metadata = {}) => {
    const response = await apiRequest('/shopify/checkouts/', {
      method: 'POST',
      body: JSON.stringify({ variant_ids: variantIds, quantities, metadata }),
    });
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || 'Failed to create checkout');
    return data;
  },

  getCheckoutStatus: async (checkoutId) => {
    const response = await apiRequest(`/shopify/checkouts/${checkoutId}/`);
    const data = await safeJson(response);
    if (!response.ok) throw new Error(data?.error || 'Failed to get checkout status');
    return data;
  },
};