/**
 * Authentication Context for managing user authentication state.
 */
import React, { createContext, useState, useEffect, useContext, useCallback } from 'react';
import { getUser, getAccessToken, setUser as storeUser } from '../utils/api';
import { authAPI } from '../utils/api';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUserState] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch user profile including free_generations_remaining
  const fetchProfile = useCallback(async () => {
    try {
      const response = await authAPI.getProfile();
      if (response.status === 'success' && response.data) {
        setProfile(response.data);
        // Update stored user with profile data
        const updatedUser = {
          ...getUser(),
          ...response.data,
        };
        storeUser(updatedUser);
        setUserState(updatedUser);
      }
    } catch (error) {
      console.error('Failed to fetch profile:', error);
    }
  }, []);

  useEffect(() => {
    // Check if user is logged in on mount
    const storedUser = getUser();
    const token = getAccessToken();
    if (storedUser && token) {
      setUserState(storedUser);
      // Fetch fresh profile data
      fetchProfile();
    }
    setLoading(false);
  }, [fetchProfile]);

  const login = async (username, password) => {
    try {
      const response = await authAPI.login(username, password);
      const userData = response.data?.user || getUser();
      setUserState(userData);
      // Fetch profile after login to get free_generations_remaining
      await fetchProfile();
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const register = async (username, email, password, passwordConfirm) => {
    try {
      const response = await authAPI.register(username, email, password, passwordConfirm);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const logout = () => {
    authAPI.logout();
    setUserState(null);
    setProfile(null);
  };

  // Refresh profile (e.g., after a generation is used)
  const refreshProfile = async () => {
    await fetchProfile();
  };

  const value = {
    user,
    profile,
    loading,
    isAuthenticated: !!user,
    freeGenerationsRemaining: profile?.free_generations_remaining ?? 0,
    totalGenerations: profile?.total_generations ?? 0,
    login,
    register,
    logout,
    refreshProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};




