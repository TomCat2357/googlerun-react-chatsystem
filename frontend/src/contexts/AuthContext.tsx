import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, getAuth, onAuthStateChanged } from 'firebase/auth';
import axios from 'axios';

interface AuthContextType {
  currentUser: User | null;
  setCurrentUser: (user: User | null) => void;
  checkAuthStatus: () => Promise<boolean>;
  setUserToken: (user: User) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const auth = getAuth();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (user) {
        const token = await user.getIdToken();
        localStorage.setItem('firebaseToken', token);
        setCurrentUser(user);
      } else {
        localStorage.removeItem('firebaseToken');
        setCurrentUser(null);
      }
    });

    return () => unsubscribe();
  }, []);

  const setUserToken = async (user: User) => {
    const token = await user.getIdToken();
    console.log('Setting new token:', token);
    localStorage.setItem('firebaseToken', token);
  };

  const checkAuthStatus = async () => {
    try {
      if (!auth.currentUser) {
        console.log('No current user found');
        return false;
      }
      const token = await auth.currentUser.getIdToken(true);
      console.log('Token obtained:', token.substring(0, 10) + '...');
      localStorage.setItem('firebaseToken', token);
      
      console.log('Making verification request to backend...');
      const response = await axios.get('http://localhost:8080/app/verify-auth', {
        withCredentials: true,
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      console.log('Backend response:', response.data);
      return response.data.status === 'success';
    } catch (error) {
      console.error('Auth check detailed error:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      return false;
    }
  };

  const value = {
    currentUser,
    setCurrentUser,
    checkAuthStatus,
    setUserToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}