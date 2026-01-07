/**
 * API utility for making requests to the backend.
 * Handles JWT token storage and authentication headers.
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

/**
 * Get stored JWT access token from localStorage
 */
export const getAccessToken = () => {
  return localStorage.getItem('access_token');
};

/**
 * Get stored JWT refresh token from localStorage
 */
export const getRefreshToken = () => {
  return localStorage.getItem('refresh_token');
};

/**
 * Store JWT tokens in localStorage
 */
export const setTokens = (accessToken, refreshToken) => {
  localStorage.setItem('access_token', accessToken);
  localStorage.setItem('refresh_token', refreshToken);
};

/**
 * Remove tokens from localStorage
 */
export const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
};

/**
 * Store user data in localStorage
 */
export const setUser = (user) => {
  localStorage.setItem('user', JSON.stringify(user));
};

/**
 * Get user data from localStorage
 */
export const getUser = () => {
  const userStr = localStorage.getItem('user');
  return userStr ? JSON.parse(userStr) : null;
};

/**
 * Make an authenticated API request
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

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Token might be expired, try to refresh
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
          setTokens(data.access, refreshToken);
          // Retry original request with new token
          headers['Authorization'] = `Bearer ${data.access}`;
          return fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers,
          });
        }
      } catch (error) {
        // Refresh failed, clear tokens
        clearTokens();
        window.location.href = '/login';
        throw new Error('Session expired. Please login again.');
      }
    }
  }

  return response;
};

/**
 * Authentication API functions
 */
export const authAPI = {
  /**
   * Register a new user
   */
  register: async (username, email, password, passwordConfirm) => {
    const response = await fetch(`${API_BASE_URL}/auth/register/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username,
        email,
        password,
        passwordConfirm,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Registration failed');
    }
    return data;
  },

  /**
   * Login user
   */
  login: async (username, password) => {
    const response = await fetch(`${API_BASE_URL}/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Login failed');
    }

    // Store tokens and user data
    if (data.data && data.data.access && data.data.refresh) {
      setTokens(data.data.access, data.data.refresh);
      if (data.data.user) {
        setUser(data.data.user);
      }
    }

    return data;
  },

  /**
   * Verify email with token
   */
  verifyEmail: async (uid, token) => {
    const response = await fetch(
      `${API_BASE_URL}/auth/verify-email/?uid=${uid}&token=${token}`
    );

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Email verification failed');
    }
    return data;
  },

  /**
   * Get current user profile including free generations remaining
   */
  getProfile: async () => {
    const response = await apiRequest('/auth/profile/');
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to get profile');
    }
    return data;
  },

  /**
   * Logout user
   */
  logout: () => {
    clearTokens();
  },
};

/**
 * Shopify API functions
 */
export const shopifyAPI = {
  /**
   * Create a Shopify checkout for meal plan purchase
   * @param {string[]} variantIds - Array of Shopify product variant IDs
   * @param {number[]} quantities - Array of quantities for each variant
   * @param {Object} metadata - Metadata to attach to checkout (e.g., { goal_id: 123 })
   */
  createCheckout: async (variantIds, quantities, metadata = {}) => {
    const response = await apiRequest('/shopify/checkouts/', {
      method: 'POST',
      body: JSON.stringify({
        variant_ids: variantIds,
        quantities: quantities,
        metadata: metadata,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to create checkout');
    }
    return data;
  },

  /**
   * Get checkout status
   * @param {number} checkoutId - Django checkout ID
   */
  getCheckoutStatus: async (checkoutId) => {
    const response = await apiRequest(`/shopify/checkouts/${checkoutId}/`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to get checkout status');
    }
    return data;
  },
};




