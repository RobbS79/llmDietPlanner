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
            gap: '0.75rem',
            alignItems: 'center',
          }}>
            <button
              onClick={() => navigate('/')}
              style={{
                minWidth: '100px',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: '0.875rem',
                transition: 'all 0.2s',
                background: isActive('/') ? '#6366f1' : 'transparent',
                color: isActive('/') ? 'white' : '#4b5563',
              }}
              onMouseEnter={(e) => {
                if (!isActive('/')) {
                  e.target.style.background = '#f3f4f6';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive('/')) {
                  e.target.style.background = 'transparent';
                }
              }}
            >
              Dashboard
            </button>
            <button
              onClick={() => navigate('/goals')}
              style={{
                minWidth: '100px',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: '0.875rem',
                transition: 'all 0.2s',
                background: isActive('/goals') ? '#6366f1' : 'transparent',
                color: isActive('/goals') ? 'white' : '#4b5563',
              }}
              onMouseEnter={(e) => {
                if (!isActive('/goals')) {
                  e.target.style.background = '#f3f4f6';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive('/goals')) {
                  e.target.style.background = 'transparent';
                }
              }}
            >
              My Goals
            </button>
            <button
              onClick={() => navigate('/profile')}
              style={{
                minWidth: '100px',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: '0.875rem',
                transition: 'all 0.2s',
                background: isActive('/profile') ? '#6366f1' : 'transparent',
                color: isActive('/profile') ? 'white' : '#4b5563',
              }}
              onMouseEnter={(e) => {
                if (!isActive('/profile')) {
                  e.target.style.background = '#f3f4f6';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive('/profile')) {
                  e.target.style.background = 'transparent';
                }
              }}
            >
              Profile
            </button>
            <button
              onClick={logout}
              style={{
                minWidth: '80px',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: '1px solid #d1d5db',
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: '0.875rem',
                transition: 'all 0.2s',
                background: 'transparent',
                color: '#4b5563',
              }}
              onMouseEnter={(e) => {
                e.target.style.background = '#f3f4f6';
              }}
              onMouseLeave={(e) => {
                e.target.style.background = 'transparent';
              }}
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}

