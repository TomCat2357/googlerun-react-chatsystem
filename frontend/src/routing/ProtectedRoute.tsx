import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { currentUser, checkAuthStatus, loading } = useAuth();
  const navigate = useNavigate();
  // ↓もしかして使っていない？
  // const [authChecked, setAuthChecked] = useState(false);


  useEffect(() => {
    const verifyAuth = async () => {
      if (loading) return;  
      // 認証チェック処理
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
  }, [loading, checkAuthStatus, navigate, currentUser]);

  if (loading) {
    return <div>認証状態確認中...</div>;  // コンポーネントのトップレベルでのローディング表示
  }

  return <>{children}</>;
}