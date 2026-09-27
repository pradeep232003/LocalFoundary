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
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  profile: null,
  loading: true,
  isSuperAdmin: false,
  signInWithGoogle: async () => ({ user: null as any, isSuperAdmin: false }),
  signOut: async () => {},
  refreshProfile: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<FirebaseUser | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const syncProfile = async (fbUser: FirebaseUser) => {
    try {
      const userRef = doc(db, 'users', fbUser.uid);
      const snap = await getDoc(userRef);
      const isSuper = isUserSuperAdmin(fbUser.email);

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
          setProfile(updated);
        } else {
          setProfile(data);
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
        setProfile(newProfile);
      }
    } catch (err) {
      console.error('Error synchronizing user profile:', err);
      // Fallback in-memory profile so UI is not blocked
      const isSuper = isUserSuperAdmin(fbUser.email);
      setProfile({
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
      });
    }
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (fbUser) => {
      setUser(fbUser);
      if (fbUser) {
        await syncProfile(fbUser);
      } else {
        setProfile(null);
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const handleSignIn = async () => {
    try {
      setLoading(true);
      const fbUser = await loginWithGoogle();
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
      });
      return { user: fbUser, isSuperAdmin: isSuper };
    } catch (error: any) {
      console.error('Sign-in failed:', error);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const handleSignOut = async () => {
    try {
      await logoutUser();
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
    if (!user) return false;
    return isUserSuperAdmin(user.email, profile?.role);
  }, [user, profile]);

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        loading,
        isSuperAdmin: isSuperAdminUser,
        signInWithGoogle: handleSignIn,
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
