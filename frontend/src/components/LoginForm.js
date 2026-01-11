/**
 * Login Form Component with Google Auth
 */
import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import './AuthForms.css';

const LoginForm = ({ onSwitchToRegister, onSuccess }) => {
  const { login } = useAuth();
  const [formData, setFormData] = useState({
    username: '',
    password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

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
      if (onSuccess) onSuccess();
    } else {
      setError(result.error || 'Login failed. Please try again.');
    }

    setLoading(false);
  };

  /**
   * Handler for Google Auth Button
   * Initiates the OAuth flow by redirecting to the backend social-auth endpoint.
   */
  const handleGoogleLogin = () => {
    setGoogleLoading(true);
    setError('');
    
    try {
      console.log("Initiating Google Login redirect...");
      
      // Determine the absolute URL to ensure the browser handles the transition correctly
      const authEndpoint = '/api/auth/google/login/';
      const absoluteUrl = window.location.origin + authEndpoint;
      
      // Use href for standard redirection behavior across all browsers
      window.location.href = absoluteUrl;
    } catch (err) {
      console.error("Google login redirection failed:", err);
      setError("Could not initialize Google login. Please try again.");
      setGoogleLoading(false);
    }
  };

  return (
    <div className="auth-form-container">
      <h2 className="auth-form-title">Login</h2>
      <p className="auth-form-subtitle">Welcome back! Please login to your account.</p>

      {error && <div className="auth-error">{error}</div>}

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
            disabled={loading || googleLoading}
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
            disabled={loading || googleLoading}
          />
        </div>

        <button 
          type="submit" 
          className="btn btn-primary btn-block" 
          disabled={loading || googleLoading}
        >
          {loading ? 'Logging in...' : 'Login'}
        </button>

        <div className="auth-divider">
          <span>OR</span>
        </div>

        <button 
          type="button" 
          className="btn btn-google btn-block" 
          onClick={handleGoogleLogin}
          disabled={loading || googleLoading}
          title="Sign in with Google"
        >
          {googleLoading ? (
            'Connecting to Google...'
          ) : (
            <>
              <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" alt="Google" style={{ width: '20px' }} />
              Sign in with Google
            </>
          )}
        </button>
      </form>

      <div className="auth-form-footer">
        <p>
          Don't have an account?{' '}
          <button 
            type="button" 
            className="link-button" 
            onClick={onSwitchToRegister}
            disabled={loading || googleLoading}
          >
            Register here
          </button>
        </p>
      </div>
    </div>
  );
};

export default LoginForm;