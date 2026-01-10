/**
 * User Profile Page
 */
import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Navigation } from '../components/Navigation';

export function UserProfilePage() {
  const { user } = useAuth();

  return (
    <div className="App">
      <Navigation />
      <div className="container" style={{ paddingTop: '2rem', paddingBottom: '4rem' }}>
        <div style={{
          background: 'white',
          padding: '2rem',
          borderRadius: '12px',
          boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
          maxWidth: '800px',
          margin: '0 auto',
        }}>
          <h1 style={{ marginBottom: '2rem', color: '#1f2937' }}>User Profile</h1>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', color: '#4b5563' }}>
                Username
              </label>
              <div style={{
                padding: '0.75rem',
                background: '#f9fafb',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
              }}>
                {user?.username || 'N/A'}
              </div>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', color: '#4b5563' }}>
                Email
              </label>
              <div style={{
                padding: '0.75rem',
                background: '#f9fafb',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
              }}>
                {user?.email || 'N/A'}
              </div>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', color: '#4b5563' }}>
                User ID
              </label>
              <div style={{
                padding: '0.75rem',
                background: '#f9fafb',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
              }}>
                {user?.id || 'N/A'}
              </div>
            </div>

            <div style={{
              marginTop: '1rem',
              padding: '1rem',
              background: '#eff6ff',
              borderRadius: '8px',
              border: '1px solid #bfdbfe',
            }}>
              <p style={{ margin: 0, color: '#1e40af', fontSize: '0.9rem' }}>
                💡 <strong>Tip:</strong> Your dietary goals and plans are securely stored and encrypted for GDPR compliance.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}





