import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import './AuthForms.css';

const LoginForm = ({ onSwitchToRegister, onSuccess }) => {
  const { login } = useAuth();
  const [formData, setFormData] = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    console.log("[Auth] LoginForm component mounted.");
  }, []);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
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
      setError(result.error || 'Login failed.');
    }
    setLoading(false);
  };

  const handleGoogleLogin = (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log("[Auth] Initiating Google Auth redirect...");
    // Hard redirect to backend to escape the React Shell
    window.location.href = window.location.origin + '/api/auth/google/login/';
  };

  return (
    <div className="auth-form-container" style={{ position: 'relative', zIndex: 10 }}>
      <h2 className="auth-form-title">Login</h2>
      <p className="auth-form-subtitle">Welcome back!</p>

      {error && <div className="auth-error">{error}</div>}

      <form onSubmit={handleSubmit} className="auth-form">
        <div className="form-group">
          <label>Username</label>
          <input type="text" name="username" value={formData.username} onChange={handleChange} required />
        </div>
        <div className="form-group">
          <label>Password</label>
          <input type="password" name="password" value={formData.password} onChange={handleChange} required />
        </div>
        <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
          {loading ? 'Processing...' : 'Login'}
        </button>

        <div className="auth-divider"><span>OR</span></div>

        <button type="button" className="btn btn-google btn-block" onClick={handleGoogleLogin}>
          <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" alt="G" style={{ width: '18px' }} />
          Sign in with Google
        </button>
      </form>
      <div className="auth-form-footer">
        <p>No account? <button type="button" className="link-button" onClick={onSwitchToRegister}>Register</button></p>
      </div>
    </div>
  );
};

export default LoginForm;