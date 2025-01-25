import { ReactNode, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { currentUser, checkAuthStatus } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const verifyAuth = async () => {
      console.log('ProtectedRoute: Starting auth verification');
      console.log('Current user state:', currentUser);
      const isAuthenticated = await checkAuthStatus();
      console.log('Authentication result:', isAuthenticated);
      if (!isAuthenticated) {
        console.log('Redirecting to login page');
        navigate('/', { replace: true });
      }
    };

    verifyAuth();
  }, [checkAuthStatus, navigate, currentUser]);

  if (!currentUser) {
    return <div>Loading...</div>;
  }

  return <>{children}</>;
}