import { initializeApp, getApps, getApp } from 'firebase/app';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
};

export const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();