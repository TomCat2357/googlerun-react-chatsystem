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
      const isAuthenticated = await checkAuthStatus();
      if (!isAuthenticated) {
        navigate('/', { replace: true });
      }
    };

    verifyAuth();
  }, [checkAuthStatus, navigate]);

  if (!currentUser) {
    return <div>Loading...</div>;
  }

  return <>{children}</>;
}