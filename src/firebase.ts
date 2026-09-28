// Firebase client configuration & initialization
import { initializeApp, getApps, getApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut as fbSignOut,
  onAuthStateChanged,
  User as FirebaseUser,
} from 'firebase/auth';
import {
  initializeFirestore,
  getFirestore,
  Firestore,
  collection,
  addDoc,
  serverTimestamp,
} from 'firebase/firestore';
import firebaseConfig from '../firebase-applet-config.json';

const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();

// Specify custom databaseId if configured
export const db: Firestore = firebaseConfig.firestoreDatabaseId
  ? initializeFirestore(app, {}, firebaseConfig.firestoreDatabaseId)
  : getFirestore(app);

export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({
  prompt: 'select_account',
});

export const SUPER_ADMIN_EMAIL = 'pradeep.verghise@googlemail.com';
export const SUPER_ADMIN_EMAILS = [
  'pradeep.verghise@googlemail.com',
  'pradeep.verghise@gmail.com',
];

export function isUserSuperAdmin(email?: string | null, role?: string | null): boolean {
  if (!email) return false;
  const normalized = email.toLowerCase().trim();
  if (SUPER_ADMIN_EMAILS.some(e => e.toLowerCase() === normalized)) return true;
  return role === 'super_admin';
}

export async function loginWithGoogle(): Promise<FirebaseUser> {
  const result = await signInWithPopup(auth, googleProvider);
  return result.user;
}

export async function logoutUser(): Promise<void> {
  await fbSignOut(auth);
}

export interface ActivityEvent {
  id?: string;
  type: 'user_login' | 'app_created' | 'app_build' | 'subscription_change' | 'audit';
  userEmail: string;
  userName?: string;
  userPhoto?: string;
  userRole?: string;
  title: string;
  description: string;
  metadata?: Record<string, any>;
  timestamp?: any;
  createdAtIso?: string;
}

/**
 * Log an activity event to Firebase Firestore for the Super Admin real-time stream
 */
export async function logActivityEvent(event: Omit<ActivityEvent, 'id' | 'timestamp'>): Promise<void> {
  try {
    const colRef = collection(db, 'activity_events');
    await addDoc(colRef, {
      ...event,
      timestamp: serverTimestamp(),
      createdAtIso: new Date().toISOString(),
    });
  } catch (err) {
    console.warn('Failed to log activity event to Firestore:', err);
  }
}

export { onAuthStateChanged };
export type { FirebaseUser };
