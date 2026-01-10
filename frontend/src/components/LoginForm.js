/**
 * Login Form Component
 */
import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import GoogleLoginButton from './GoogleLoginButton';
import SocialAuthDivider from './SocialAuthDivider';
import './AuthForms.css';

const LoginForm = ({ onSwitchToRegister, onSuccess }) => {
  const { login } = useAuth();
  const [formData, setFormData] = useState({
    username: '',
    password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSocialSuccess = () => {
    if (onSuccess) {
      onSuccess();
    }
  };

  const handleSocialError = (errorMessage) => {
    setError(errorMessage || 'Social login failed. Please try again.');
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError(''); // Clear error on input change
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const result = await login(formData.username, formData.password);

    if (result.success) {
      if (onSuccess) {
        onSuccess();
      }
    } else {
      setError(result.error || 'Login failed. Please try again.');
    }

    setLoading(false);
  };

  return (
    <div className="auth-form-container">
      <h2 className="auth-form-title">Login</h2>
      <p className="auth-form-subtitle">Welcome back! Please login to your account.</p>

      {error && <div className="auth-error">{error}</div>}

      <div className="social-auth-buttons">
        <GoogleLoginButton
          onSuccess={handleSocialSuccess}
          onError={handleSocialError}
          text="Sign in with Google"
        />
      </div>

      <SocialAuthDivider text="or sign in with email" />

      <form onSubmit={handleSubmit} className="auth-form">
        <div className="form-group">
          <label htmlFor="username">Username or Email</label>
          <input
            type="text"
            id="username"
            name="username"
            value={formData.username}
            onChange={handleChange}
            required
            autoComplete="username"
            placeholder="Enter your username or email"
          />
        </div>

        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            type="password"
            id="password"
            name="password"
            value={formData.password}
            onChange={handleChange}
            required
            autoComplete="current-password"
            placeholder="Enter your password"
          />
        </div>

        <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
          {loading ? 'Logging in...' : 'Login'}
        </button>
      </form>

      <div className="auth-form-footer">
        <p>
          Don't have an account?{' '}
          <button type="button" className="link-button" onClick={onSwitchToRegister}>
            Register here
          </button>
        </p>
      </div>
    </div>
  );
};

export default LoginForm;





