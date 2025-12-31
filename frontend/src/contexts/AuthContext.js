/**
 * Authentication Context for managing user authentication state.
 */
import React, { createContext, useState, useEffect, useContext } from 'react';
import { getUser, getAccessToken } from '../utils/api';
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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is logged in on mount
    const storedUser = getUser();
    const token = getAccessToken();
    if (storedUser && token) {
      setUserState(storedUser);
    }
    setLoading(false);
  }, []);

  const login = async (username, password) => {
    try {
      const response = await authAPI.login(username, password);
      const userData = response.data?.user || getUser();
      setUserState(userData);
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
  };

  const value = {
    user,
    loading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

