/**
 * Registration Form Component
 */
import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import './AuthForms.css';

const RegistrationForm = ({ onSwitchToLogin, onSuccess }) => {
  const { register } = useAuth();
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    passwordConfirm: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError(''); // Clear error on input change
  };

  const validateForm = () => {
    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters long');
      return false;
    }

    if (formData.password !== formData.passwordConfirm) {
      setError('Passwords do not match');
      return false;
    }

    if (!/\d/.test(formData.password)) {
      setError('Password must contain at least one digit');
      return false;
    }

    if (!/[a-zA-Z]/.test(formData.password)) {
      setError('Password must contain at least one letter');
      return false;
    }

    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess(false);

    if (!validateForm()) {
      return;
    }

    setLoading(true);

    const result = await register(
      formData.username,
      formData.email,
      formData.password,
      formData.passwordConfirm
    );

    if (result.success) {
      setSuccess(true);
      if (onSuccess) {
        onSuccess(result.data);
      }
    } else {
      setError(result.error || 'Registration failed. Please try again.');
    }

    setLoading(false);
  };

  if (success) {
    return (
      <div className="auth-form-container">
        <div className="auth-success">
          <h2 className="auth-form-title">Registration Successful!</h2>
          <p>
            Thank you for registering. We've sent a verification email to{' '}
            <strong>{formData.email}</strong>.
          </p>
          <p>Please check your email and click the verification link to activate your account.</p>
          <button type="button" className="btn btn-primary btn-block" onClick={onSwitchToLogin}>
            Go to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-form-container">
      <h2 className="auth-form-title">Create Account</h2>
      <p className="auth-form-subtitle">Sign up to start planning your diet today.</p>

      {error && <div className="auth-error">{error}</div>}

      <form onSubmit={handleSubmit} className="auth-form">
        <div className="form-group">
          <label htmlFor="reg-username">Username</label>
          <input
            type="text"
            id="reg-username"
            name="username"
            value={formData.username}
            onChange={handleChange}
            required
            minLength={3}
            maxLength={150}
            autoComplete="username"
            placeholder="Choose a username (3-150 characters)"
          />
        </div>

        <div className="form-group">
          <label htmlFor="reg-email">Email</label>
          <input
            type="email"
            id="reg-email"
            name="email"
            value={formData.email}
            onChange={handleChange}
            required
            autoComplete="email"
            placeholder="Enter your email address"
          />
        </div>

        <div className="form-group">
          <label htmlFor="reg-password">Password</label>
          <input
            type="password"
            id="reg-password"
            name="password"
            value={formData.password}
            onChange={handleChange}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="At least 8 characters with letters and numbers"
          />
        </div>

        <div className="form-group">
          <label htmlFor="reg-password-confirm">Confirm Password</label>
          <input
            type="password"
            id="reg-password-confirm"
            name="passwordConfirm"
            value={formData.passwordConfirm}
            onChange={handleChange}
            required
            minLength={8}
            autoComplete="new-password"
            placeholder="Confirm your password"
          />
        </div>

        <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
          {loading ? 'Creating Account...' : 'Register'}
        </button>
      </form>

      <div className="auth-form-footer">
        <p>
          Already have an account?{' '}
          <button type="button" className="link-button" onClick={onSwitchToLogin}>
            Login here
          </button>
        </p>
      </div>
    </div>
  );
};

export default RegistrationForm;




