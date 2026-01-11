/**
 * Login Form Component with robust Google Auth redirection.
 */
import React, { useState, useEffect } from 'react';
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

  // Lifecycle check to confirm the component is active in production
  useEffect(() => {
    console.log("[Auth] LoginForm mounted successfully.");
  }, []);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError('');
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
   * Hard redirect to backend Google Login.
   * We use a manual click handler to ensure we bypass any React Event synthetic lag.
   */
  const handleGoogleLogin = (e) => {
    // Stop all other events to prevent form submission or bubble blocking
    e.preventDefault();
    e.stopPropagation();
    
    console.log("[GoogleAuth] Redirect initiated to /api/auth/google/login/");
    
    // Construct absolute URL to force the browser to leave the React SPA
    const target = window.location.origin + '/api/auth/google/login/';
    
    // Perform hard navigation
    window.location.assign(target);
  };

  return (
    /* We use z-index and relative positioning to ensure no invisible overlays block the click */
    <div className="auth-form-container" style={{ position: 'relative', zIndex: 100 }}>
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

        <div className="auth-divider">
          <span>OR</span>
        </div>

        {/* Using a styled link for the Google button is more reliable for external redirects */}
        <a 
          href="/api/auth/google/login/" 
          className="btn btn-google btn-block"
          onClick={handleGoogleLogin}
          style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" alt="Google" style={{ width: '20px', marginRight: '10px' }} />
          Sign in with Google
        </a>
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