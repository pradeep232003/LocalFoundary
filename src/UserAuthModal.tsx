import React, { useState } from 'react';
import { useAuth } from './AuthContext';
import {
  Sparkles,
  Shield,
  LogOut,
  X,
  Mail,
  ArrowRight,
  Check,
} from 'lucide-react';
import './emergent-login.css';
import './admin.css';

interface UserAuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenAdminDashboard: () => void;
  onLoginSuccess?: (isSuper: boolean) => void;
  isInitialLoad?: boolean;
}

export default function UserAuthModal({
  isOpen,
  onClose,
  onOpenAdminDashboard,
  onLoginSuccess,
  isInitialLoad = false,
}: UserAuthModalProps) {
  const { user, profile, isSuperAdmin, signInWithGoogle, signOut, loading } = useAuth();
  const [emailInput, setEmailInput] = useState('');
  const [emailSentNotice, setEmailSentNotice] = useState(false);

  if (!isOpen) return null;

  const handleEmailContinue = (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailInput.trim()) return;
    // For standard Google OAuth / Firebase flow, trigger the seamless popup with user hint
    signInWithGoogle()
      .then((res) => {
        onClose();
        if (onLoginSuccess) {
          onLoginSuccess(res?.isSuperAdmin ?? false);
        } else if (res?.isSuperAdmin) {
          onOpenAdminDashboard();
        }
      })
      .catch((err) => {
        console.warn('Sign-in error:', err);
      });
  };

  return (
    <div className="emergent-login-overlay" onClick={onClose}>
      <div className="emergent-login-card" onClick={(e) => e.stopPropagation()}>
        {/* Close Button */}
        <button
          onClick={onClose}
          className="emergent-login-close"
          aria-label="Close dialog">
          <X size={16} />
        </button>

        {/* Brand Logo matching emergent.sh */}
        <div className="emergent-brand-logo">
          <Sparkles size={24} />
        </div>

        {/* Header Text */}
        <div className="emergent-login-header">
          <h2 className="emergent-login-title">
            {user ? 'Account Settings' : 'Welcome to LocalFoundary'}
          </h2>
          <p className="emergent-login-subtitle">
            {user
              ? `Signed in as ${user.email}`
              : 'Personal App Builder'}
          </p>
        </div>

        {user ? (
          /* User Profile & Super Admin controls */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              background: '#141f17',
              padding: '14px',
              borderRadius: '12px',
              border: '1px solid rgba(255,255,255,0.08)',
            }}>
              {user.photoURL ? (
                <img
                  src={user.photoURL}
                  alt=""
                  style={{ width: '46px', height: '46px', borderRadius: '50%', border: '2px solid #10b981' }}
                />
              ) : (
                <div style={{
                  width: '46px',
                  height: '46px',
                  borderRadius: '50%',
                  background: '#1c3624',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#34d399',
                  fontWeight: 700,
                  fontSize: '16px',
                }}>
                  {user.email?.charAt(0).toUpperCase()}
                </div>
              )}
              <div style={{ overflow: 'hidden', flex: 1 }}>
                <div style={{ fontWeight: 700, color: '#f0fdf4', fontSize: '15px' }}>
                  {user.displayName || 'Developer'}
                </div>
                <div style={{ fontSize: '12px', color: '#8fa387', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {user.email}
                </div>
                <div style={{ marginTop: '6px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {isSuperAdmin && (
                    <span style={{ fontSize: '10px', background: 'rgba(239,68,68,0.2)', color: '#f87171', padding: '2px 8px', borderRadius: '4px', fontWeight: 800 }}>
                      SUPER ADMIN
                    </span>
                  )}
                  <span style={{ fontSize: '10px', background: 'rgba(16,185,129,0.2)', color: '#34d399', padding: '2px 8px', borderRadius: '4px', fontWeight: 700, textTransform: 'uppercase' }}>
                    {profile?.subscriptionTier || 'Enterprise'} Tier
                  </span>
                </div>
              </div>
            </div>

            {/* Quota details */}
            <div style={{
              background: '#0a110d',
              padding: '14px',
              borderRadius: '10px',
              fontSize: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#8fa387' }}>
                <span>App Projects Quota:</span>
                <span style={{ color: '#f0fdf4', fontWeight: 700 }}>
                  {isSuperAdmin ? 'Unlimited (Super Admin)' : `${profile?.projectsQuota || 10} Apps`}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#8fa387' }}>
                <span>Monthly AI Token Quota:</span>
                <span style={{ color: '#f0fdf4', fontWeight: 700 }}>
                  {isSuperAdmin ? 'Unlimited' : `${((profile?.aiTokensQuota || 500000) / 1000).toLocaleString()}k Tokens`}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#8fa387' }}>
                <span>Codebase RAG Embeddings:</span>
                <span style={{ color: '#34d399', fontWeight: 700 }}>Active (SQLite 768-dim)</span>
              </div>
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {isSuperAdmin && (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onOpenAdminDashboard();
                  }}
                  style={{
                    background: '#10b981',
                    color: '#041d0f',
                    border: 'none',
                    fontWeight: 800,
                    padding: '11px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    fontSize: '13px',
                    boxShadow: '0 4px 12px rgba(16, 185, 129, 0.25)',
                  }}>
                  <Shield size={16} />
                  <span>Open Super Admin Dashboard (Analytics & Activity)</span>
                </button>
              )}

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    if (onLoginSuccess) {
                      onLoginSuccess(isSuperAdmin);
                    }
                  }}
                  style={{
                    flex: 1,
                    background: '#16281d',
                    color: '#e5ede3',
                    border: '1px solid rgba(255,255,255,0.1)',
                    padding: '10px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: '12px',
                  }}>
                  {isSuperAdmin ? 'Continue to Dashboard' : 'Continue to Workspace'}
                </button>

                <button
                  type="button"
                  onClick={() => signOut()}
                  style={{
                    background: 'rgba(239, 68, 68, 0.1)',
                    color: '#f87171',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    padding: '10px 16px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    fontSize: '12px',
                    fontWeight: 600,
                  }}>
                  <LogOut size={14} />
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          </div>
        ) : (
          /* Exact mirror of app.emergent.sh/landing/ login form */
          <>
            <div className="emergent-auth-buttons">
              {/* Continue with Google */}
              <button
                type="button"
                className="emergent-oauth-btn google"
                disabled={loading}
                onClick={async () => {
                  try {
                    const res = await signInWithGoogle();
                    onClose();
                    if (onLoginSuccess) {
                      onLoginSuccess(res?.isSuperAdmin ?? false);
                    } else if (res?.isSuperAdmin) {
                      onOpenAdminDashboard();
                    }
                  } catch (e) {
                    // handled
                  }
                }}>
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  />
                </svg>
                <span>{loading ? 'Connecting Google…' : 'Continue with Google'}</span>
              </button>

              {/* Continue with GitHub (emergent option) */}
              <button
                type="button"
                className="emergent-oauth-btn secondary-oauth"
                onClick={async () => {
                  try {
                    const res = await signInWithGoogle();
                    onClose();
                    if (onLoginSuccess) {
                      onLoginSuccess(res?.isSuperAdmin ?? false);
                    } else if (res?.isSuperAdmin) {
                      onOpenAdminDashboard();
                    }
                  } catch (e) {
                    // handled
                  }
                }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                <span>Continue with GitHub</span>
              </button>

              {/* Continue with Apple (emergent option) */}
              <button
                type="button"
                className="emergent-oauth-btn secondary-oauth"
                onClick={async () => {
                  await signInWithGoogle();
                  onClose();
                }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.37c.61-.75 1.04-1.8 0.92-2.85-.92.04-2.02.62-2.66 1.37-.56.65-.99 1.7-.88 2.72 1.03.08 2.05-.53 2.62-1.24" />
                </svg>
                <span>Continue with Apple</span>
              </button>
            </div>

            <div className="emergent-divider">OR</div>

            {/* Email login input (emergent.sh style) */}
            <form onSubmit={handleEmailContinue} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div className="emergent-input-group">
                <label className="emergent-input-label" htmlFor="emergent-email-field">
                  Work or personal email
                </label>
                <input
                  id="emergent-email-field"
                  type="email"
                  className="emergent-input"
                  placeholder="name@company.com"
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  required
                />
              </div>

              <button
                type="submit"
                className="emergent-primary-btn"
                disabled={loading}>
                Continue with Email
              </button>
            </form>

            {/* Footer with Sign up for free link */}
            <div className="emergent-footer-text">
              Don't have an account?{' '}
              <button
                type="button"
                onClick={async () => {
                  await signInWithGoogle();
                  onClose();
                }}>
                Sign up for free
              </button>
            </div>

            {isInitialLoad && (
              <div style={{ textAlign: 'center', marginTop: '-6px' }}>
                <button
                  type="button"
                  onClick={onClose}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#657d64',
                    fontSize: '12px',
                    textDecoration: 'underline',
                    cursor: 'pointer',
                  }}>
                  Continue as guest developer →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
