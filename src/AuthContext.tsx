import React, { createContext, useContext, useEffect, useState, useMemo } from 'react';
import {
  auth,
  db,
  loginWithGoogle,
  logoutUser,
  onAuthStateChanged,
  isUserSuperAdmin,
  SUPER_ADMIN_EMAIL,
  FirebaseUser,
  logActivityEvent,
} from './firebase';
import {
  doc,
  getDoc,
  setDoc,
  serverTimestamp,
} from 'firebase/firestore';

export interface UserProfile {
  uid: string;
  email: string;
  displayName: string;
  photoURL: string;
  role: 'super_admin' | 'subscriber' | 'member';
  subscriptionTier: 'free' | 'starter' | 'pro' | 'enterprise';
  subscriptionStatus: 'active' | 'past_due' | 'canceled' | 'trialing';
  projectsQuota: number;
  aiTokensQuota: number;
  aiTokensUsed: number;
  createdAt?: any;
  updatedAt?: any;
}

interface AuthContextType {
  user: FirebaseUser | null;
  profile: UserProfile | null;
  loading: boolean;
  isSuperAdmin: boolean;
  signInWithGoogle: () => Promise<{ user: FirebaseUser; isSuperAdmin: boolean }>;
  loginWithEmail: (email: string, displayName?: string) => Promise<{ user: any; isSuperAdmin: boolean }>;
  loginAsSuperAdmin: () => Promise<{ user: any; isSuperAdmin: boolean }>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AUTH_STORAGE_KEY = 'localfoundry:auth_session';

const AuthContext = createContext<AuthContextType>({
  user: null,
  profile: null,
  loading: false,
  isSuperAdmin: false,
  signInWithGoogle: async () => ({ user: null as any, isSuperAdmin: false }),
  loginWithEmail: async () => ({ user: null as any, isSuperAdmin: false }),
  loginAsSuperAdmin: async () => ({ user: null as any, isSuperAdmin: false }),
  signOut: async () => {},
  refreshProfile: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Read initial user synchronously from localStorage if present
  const [user, setUser] = useState<FirebaseUser | null>(() => {
    try {
      const saved = localStorage.getItem(AUTH_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.user || null;
      }
    } catch (e) {
      console.warn('Error reading stored session:', e);
    }
    return null;
  });

  const [profile, setProfile] = useState<UserProfile | null>(() => {
    try {
      const saved = localStorage.getItem(AUTH_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.profile || null;
      }
    } catch (e) {}
    return null;
  });

  const [loading, setLoading] = useState<boolean>(false);

  const syncProfile = async (fbUser: FirebaseUser) => {
    try {
      const userRef = doc(db, 'users', fbUser.uid);
      const snap = await getDoc(userRef);
      const isSuper = isUserSuperAdmin(fbUser.email);

      let effectiveProfile: UserProfile;

      if (snap.exists()) {
        const data = snap.data() as UserProfile;
        // ensure super admin email always holds super_admin role
        if (isSuper && data.role !== 'super_admin') {
          const updated = {
            ...data,
            role: 'super_admin' as const,
            subscriptionTier: 'enterprise' as const,
            subscriptionStatus: 'active' as const,
            updatedAt: serverTimestamp(),
          };
          await setDoc(userRef, updated, { merge: true });
          effectiveProfile = updated;
        } else {
          effectiveProfile = data;
        }
      } else {
        // Initial creation
        const newProfile: UserProfile = {
          uid: fbUser.uid,
          email: fbUser.email || '',
          displayName: fbUser.displayName || 'Developer',
          photoURL: fbUser.photoURL || '',
          role: isSuper ? 'super_admin' : 'subscriber',
          subscriptionTier: isSuper ? 'enterprise' : 'starter',
          subscriptionStatus: 'active',
          projectsQuota: isSuper ? 9999 : 10,
          aiTokensQuota: isSuper ? 10000000 : 500000,
          aiTokensUsed: 0,
          createdAt: serverTimestamp(),
          updatedAt: serverTimestamp(),
        };
        await setDoc(userRef, newProfile);
        effectiveProfile = newProfile;
      }

      setProfile(effectiveProfile);
      try {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ user: fbUser, profile: effectiveProfile }));
      } catch (err) {}
    } catch (err) {
      console.error('Error synchronizing user profile:', err);
      // Fallback in-memory profile so UI is not blocked
      const isSuper = isUserSuperAdmin(fbUser.email);
      const fallback: UserProfile = {
        uid: fbUser.uid,
        email: fbUser.email || '',
        displayName: fbUser.displayName || 'Developer',
        photoURL: fbUser.photoURL || '',
        role: isSuper ? 'super_admin' : 'subscriber',
        subscriptionTier: isSuper ? 'enterprise' : 'starter',
        subscriptionStatus: 'active',
        projectsQuota: isSuper ? 9999 : 10,
        aiTokensQuota: isSuper ? 10000000 : 500000,
        aiTokensUsed: 0,
      };
      setProfile(fallback);
      try {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ user: fbUser, profile: fallback }));
      } catch (e) {}
    }
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (fbUser) => {
      if (fbUser) {
        setUser(fbUser);
        await syncProfile(fbUser);
      } else {
        // If Firebase auth is null but we had an explicit stored session (e.g. email / super admin login), preserve it
        const saved = localStorage.getItem(AUTH_STORAGE_KEY);
        if (!saved) {
          setUser(null);
          setProfile(null);
        }
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const handleSignIn = async () => {
    try {
      setLoading(true);
      const fbUser = await loginWithGoogle();
      setUser(fbUser);
      await syncProfile(fbUser);
      const isSuper = isUserSuperAdmin(fbUser.email);
      await logActivityEvent({
        type: 'user_login',
        userEmail: fbUser.email || '',
        userName: fbUser.displayName || 'Developer',
        userPhoto: fbUser.photoURL || '',
        userRole: isSuper ? 'super_admin' : 'subscriber',
        title: isSuper ? 'Super Admin Google Sign-in' : 'Subscriber Google Sign-in',
        description: `Authenticated via Google OAuth into LocalFoundry platform (${fbUser.email})`,
        metadata: {
          uid: fbUser.uid,
          provider: 'google.com',
        },
      }).catch(() => {});
      return { user: fbUser, isSuperAdmin: isSuper };
    } catch (error: any) {
      console.error('Sign-in failed:', error);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const loginWithEmail = async (email: string, displayName?: string) => {
    setLoading(true);
    try {
      const cleanEmail = email.trim();
      const isSuper = isUserSuperAdmin(cleanEmail);
      const uid = 'user_' + cleanEmail.replace(/[^a-zA-Z0-9]/g, '_');
      const standardUser: any = {
        uid,
        email: cleanEmail,
        displayName: displayName || (isSuper ? 'Pradeep Verghise' : cleanEmail.split('@')[0]),
        photoURL: '',
      };

      const userProfile: UserProfile = {
        uid,
        email: cleanEmail,
        displayName: displayName || (isSuper ? 'Pradeep Verghise' : cleanEmail.split('@')[0]),
        photoURL: '',
        role: isSuper ? 'super_admin' : 'subscriber',
        subscriptionTier: isSuper ? 'enterprise' : 'starter',
        subscriptionStatus: 'active',
        projectsQuota: isSuper ? 9999 : 10,
        aiTokensQuota: isSuper ? 10000000 : 500000,
        aiTokensUsed: 0,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      setUser(standardUser);
      setProfile(userProfile);
      try {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ user: standardUser, profile: userProfile }));
      } catch (e) {}

      // Best effort persist to Firestore
      try {
        const userRef = doc(db, 'users', uid);
        await setDoc(userRef, {
          ...userProfile,
          updatedAt: serverTimestamp(),
        }, { merge: true });
      } catch (err) {
        console.warn('Firestore user save warning:', err);
      }

      await logActivityEvent({
        type: 'user_login',
        userEmail: cleanEmail,
        userName: userProfile.displayName,
        userPhoto: '',
        userRole: userProfile.role,
        title: isSuper ? 'Super Admin Email Sign-in' : 'Subscriber Email Sign-in',
        description: `Direct session initiated for ${cleanEmail}`,
        metadata: { provider: 'email', isSuperAdmin: isSuper },
      }).catch(() => {});

      return { user: standardUser, isSuperAdmin: isSuper };
    } finally {
      setLoading(false);
    }
  };

  const loginAsSuperAdmin = async () => {
    return loginWithEmail(SUPER_ADMIN_EMAIL, 'Pradeep Verghise');
  };

  const handleSignOut = async () => {
    try {
      localStorage.removeItem(AUTH_STORAGE_KEY);
      await logoutUser().catch(() => {});
      setUser(null);
      setProfile(null);
    } catch (error) {
      console.error('Sign-out failed:', error);
    }
  };

  const refreshProfile = async () => {
    if (user) {
      await syncProfile(user);
    }
  };

  const isSuperAdminUser = useMemo(() => {
    const email = user?.email || profile?.email;
    if (!email) return false;
    return isUserSuperAdmin(email, profile?.role);
  }, [user, profile]);

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        loading,
        isSuperAdmin: isSuperAdminUser,
        signInWithGoogle: handleSignIn,
        loginWithEmail,
        loginAsSuperAdmin,
        signOut: handleSignOut,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
