/**
 * Navigation Component - Reusable navigation bar
 */
import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function Navigation() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const isActive = (path) => location.pathname === path;

  return (
    <nav style={{
      background: 'rgba(255, 255, 255, 0.95)',
      backdropFilter: 'blur(10px)',
      padding: '1rem 0',
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
      position: 'sticky',
      top: 0,
      zIndex: 1000,
    }}>
      <div className="container">
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          {/* Logo/Brand */}
          <div
            onClick={() => navigate('/')}
            style={{
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <span style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#6366f1' }}>
              🍎
            </span>
            <span style={{ fontSize: '1.25rem', fontWeight: '600', color: '#1f2937' }}>
              LLM Diet Planner
            </span>
          </div>

          {/* Navigation Links */}
          <div style={{
            display: 'flex',
            gap: '1rem',
            alignItems: 'center',
          }}>
            <button
              onClick={() => navigate('/')}
              className={`btn ${isActive('/') ? 'btn-primary' : 'btn-secondary'}`}
              style={{ minWidth: '100px' }}
            >
              Dashboard
            </button>
            <button
              onClick={() => navigate('/goals')}
              className={`btn ${isActive('/goals') ? 'btn-primary' : 'btn-secondary'}`}
              style={{ minWidth: '100px' }}
            >
              My Goals
            </button>
            <button
              onClick={() => navigate('/profile')}
              className={`btn ${isActive('/profile') ? 'btn-primary' : 'btn-secondary'}`}
              style={{ minWidth: '100px' }}
            >
              Profile
            </button>
            <button
              onClick={logout}
              className="btn btn-secondary"
              style={{ minWidth: '80px' }}
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}

