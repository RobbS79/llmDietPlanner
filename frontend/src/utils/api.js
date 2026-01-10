/**
 * API utility for making requests to the backend.
 * Handles JWT token storage, authentication headers, and safe response parsing.
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
  if (accessToken) localStorage.setItem('access_token', accessToken);
  if (refreshToken) localStorage.setItem('refresh_token', refreshToken);
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
 * Helper to safely parse JSON from a response.
 * Prevents crashes when the server returns 500 HTML error pages.
 */
const safeJson = async (response) => {
  try {
    return await response.json();
  } catch (err) {
    return null; // Return null if parsing fails
  }
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

  try {
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
            // Update tokens - keep old refresh token if new one isn't provided
            setTokens(data.access, data.refresh || refreshToken);
            
            // Retry original request with new token
            headers['Authorization'] = `Bearer ${data.access}`;
            return fetch(`${API_BASE_URL}${endpoint}`, {
              ...options,
              headers,
            });
          } else {
            // Refresh token invalid
            throw new Error('Refresh failed');
          }
        } catch (error) {
          // Refresh failed, clear tokens and redirect
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

    const data = await safeJson(response);
    
    if (!response.ok) {
      const errorMsg = data?.error || data?.detail || response.statusText || 'Registration failed';
      throw new Error(errorMsg);
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

    const data = await safeJson(response);

    if (!response.ok) {
      const errorMsg = data?.error || data?.detail || response.statusText || 'Login failed';
      throw new Error(errorMsg);
    }

    // Store tokens and user data
    if (data?.data?.access && data?.data?.refresh) {
      setTokens(data.data.access, data.data.refresh);
      if (data.data.user) {
        setUser(data.data.user);
      }
    } else if (data?.access && data?.refresh) {
      // Handle standard SimpleJWT response format
      setTokens(data.access, data.refresh);
      if (data.user) setUser(data.user);
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

    const data = await safeJson(response);
    
    if (!response.ok) {
      throw new Error(data?.error || response.statusText || 'Email verification failed');
    }
    return data;
  },

  /**
   * Get current user profile including free generations remaining
   */
  getProfile: async () => {
    const response = await apiRequest('/auth/profile/');
    const data = await safeJson(response);

    if (!response.ok) {
      // If we get a 500 error (like from the LLM service crash), data will be null
      const errorMsg = data?.error || data?.detail || response.statusText || 'Failed to get profile';
      throw new Error(errorMsg);
    }
    return data;
  },

  /**
   * Logout user
   */
  logout: () => {
    clearTokens();
  },

  /**
   * Google OAuth login - sends access token to backend
   */
  googleLogin: async (accessToken) => {
    console.log('[API] googleLogin: Sending request to backend...');
    const response = await fetch(`${API_BASE_URL}/auth/google/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: accessToken }),
    });

    const data = await safeJson(response);

    if (!response.ok) {
      console.error('[API] googleLogin: Request failed:', data?.error);
      throw new Error(data?.error || response.statusText || 'Google login failed');
    }

    // Store tokens and user data
    // Handles both wrapped { data: { access... } } and flat { access... } structures
    const payload = data?.data || data;
    
    if (payload && payload.access && payload.refresh) {
      console.log('[API] googleLogin: Storing tokens in localStorage');
      setTokens(payload.access, payload.refresh);
      if (payload.user) {
        setUser(payload.user);
      }
    } else {
      console.warn('[API] googleLogin: Tokens not found in response');
    }

    return data;
  },

  /**
   * Facebook OAuth login - sends access token to backend
   */
  facebookLogin: async (accessToken) => {
    const response = await fetch(`${API_BASE_URL}/auth/facebook/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: accessToken }),
    });

    const data = await safeJson(response);
    
    if (!response.ok) {
      throw new Error(data?.error || response.statusText || 'Facebook login failed');
    }

    // Store tokens and user data
    const payload = data?.data || data;
    if (payload && payload.access && payload.refresh) {
      setTokens(payload.access, payload.refresh);
      if (payload.user) {
        setUser(payload.user);
      }
    }

    return data;
  },
};

/**
 * Shopify API functions
 */
export const shopifyAPI = {
  /**
   * Create a Shopify checkout for meal plan purchase
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

    const data = await safeJson(response);
    
    if (!response.ok) {
      throw new Error(data?.error || response.statusText || 'Failed to create checkout');
    }
    return data;
  },

  /**
   * Get checkout status
   */
  getCheckoutStatus: async (checkoutId) => {
    const response = await apiRequest(`/shopify/checkouts/${checkoutId}/`);
    const data = await safeJson(response);
    
    if (!response.ok) {
      throw new Error(data?.error || response.statusText || 'Failed to get checkout status');
    }
    return data;
  },
};