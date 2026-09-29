import React, { useState } from 'react';
import { useAuth } from './AuthContext';
export default function UserAuthModal({ isOpen, onClose, onOpenAdminDashboard, onLoginSuccess }: {
  isOpen: boolean; onClose: () => void; onOpenAdminDashboard: () => void;
  onLoginSuccess?: (owner: boolean) => void;
}) {
  const { user, unlock, signOut, loading } = useAuth();
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  if (!isOpen) return null;
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError('');
    try { await unlock(token); setToken(''); onClose(); onLoginSuccess?.(true); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not unlock workspace.'); }
  }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="unlock-title">
    <button onClick={onClose} aria-label="Close dialog">Close</button>
    <h2 id="unlock-title">{user ? 'Workspace session' : 'Unlock your workspace'}</h2>
    <p>This is a personal workspace on this computer. Use the launch link from the local launcher or enter its BUILDER_TOKEN.</p>
    {user ? <><p>Authenticated by the local backend.</p><button onClick={() => { onClose(); onOpenAdminDashboard(); }}>Workspace overview</button><button onClick={signOut}>Lock workspace</button></> :
      <form onSubmit={submit}><label>Workspace token<input autoFocus type="password" autoComplete="off" required minLength={32} value={token} onChange={e => setToken(e.target.value)} /></label>
        <button className="primary" disabled={loading}>{loading ? 'Checking…' : 'Unlock'}</button></form>}
    {error && <p role="alert">{error}</p>}
  </section></div>;
}
