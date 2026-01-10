/**
 * Social Auth Divider Component
 * Visual separator between social auth and email/password forms
 */
import React from 'react';

const SocialAuthDivider = ({ text = 'or' }) => {
  return (
    <div className="social-auth-divider">
      <span className="divider-line"></span>
      <span className="divider-text">{text}</span>
      <span className="divider-line"></span>
    </div>
  );
};

export default SocialAuthDivider;
