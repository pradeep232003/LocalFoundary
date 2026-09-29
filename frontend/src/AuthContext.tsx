import React, { createContext, useContext, useEffect, useState } from 'react';
import { request } from './api';

type Owner = { uid: string; email: string; displayName: string; photoURL: string };
type Session = {
  user: Owner | null; profile: { subscriptionTier: string } | null;
  loading: boolean; isSuperAdmin: boolean;
  unlock: (token: string) => Promise<void>; signOut: () => Promise<void>;
};
const Context = createContext<Session | null>(null);
const owner: Owner = { uid: 'local-owner', email: 'Personal workspace', displayName: 'Workspace owner', photoURL: '' };
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Owner | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    // Never reuse the prototype's unverified email/profile session.
    localStorage.removeItem('localfoundry:auth_session');
    request('/config').then(() => setUser(owner)).catch(() => setUser(null)).finally(() => setLoading(false));
  }, []);
  async function unlock(token: string) {
    setLoading(true);
    sessionStorage.setItem('foundry-token', token.trim());
    try {
      await request('/config');
      setUser(owner);
      // Refresh project/config state only after the backend accepts the token.
      window.dispatchEvent(new Event('foundry-unlocked'));
    } catch (error) {
      sessionStorage.removeItem('foundry-token');
      setUser(null);
      throw error;
    } finally { setLoading(false); }
  }
  async function signOut() {
    sessionStorage.removeItem('foundry-token');
    setUser(null);
    location.reload();
  }
  return <Context.Provider value={{ user, profile: user ? { subscriptionTier: 'Personal' } : null, loading,
    isSuperAdmin: Boolean(user), unlock, signOut }}>{children}</Context.Provider>;
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error('AuthProvider is required.');
  return value;
}
