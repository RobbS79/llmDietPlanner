import React, { createContext, useState, useEffect, useContext, useCallback } from 'react';
import { getUser, getAccessToken, setUser as storeUser, authAPI } from '../utils/api';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUserState] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async () => {
    try {
      const response = await authAPI.getProfile();
      if (response.status === 'success' && response.data) {
        setProfile(response.data);
        const updatedUser = { ...getUser(), ...response.data };
        storeUser(updatedUser);
        setUserState(updatedUser);
      }
    } catch (error) {
      console.error('[AuthContext] Failed to fetch profile:', error);
    }
  }, []);

  useEffect(() => {
    const storedUser = getUser();
    const token = getAccessToken();
    if (storedUser && token) {
      setUserState(storedUser);
      fetchProfile();
    }
    setLoading(false);
  }, [fetchProfile]);

  const login = async (username, password) => {
    try {
      const response = await authAPI.login(username, password);
      const userData = response.data?.user || getUser();
      setUserState(userData);
      await fetchProfile();
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const socialLogin = async (provider, accessToken) => {
    try {
      let response = provider === 'google' 
        ? await authAPI.googleLogin(accessToken) 
        : await authAPI.facebookLogin(accessToken);

      const userData = response.data?.user || response.user || getUser();
      setUserState(userData);
      await fetchProfile();
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

  return (
    <AuthContext.Provider value={{
      user, profile, loading, isAuthenticated: !!user,
      login, socialLogin, logout, refreshProfile: fetchProfile
    }}>
      {children}
    </AuthContext.Provider>
  );
};