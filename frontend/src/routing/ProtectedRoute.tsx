import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import PageLoader from '../utils/PageLoader';
import * as Config from "../config";

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { currentUser, checkAuthStatus, loading } = useAuth();
  const navigate = useNavigate();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const verifyAuth = async () => {
      if (loading) return;

      try {
        console.log('ProtectedRoute: Starting auth verification');
        const isAuthenticated = await checkAuthStatus();
        console.log('Authentication result:', isAuthenticated);

        if (!isMounted) return;

        // frontend/src/routing/ProtectedRoute.tsx のリダイレクト部分を修正
        if (!isAuthenticated) {
          console.log('Redirecting to login page');
          navigate(Config.getClientPath('/'), { replace: true });
        } else {
          setAuthChecked(true);
        }
      } catch (error) {
        console.error('認証チェックエラー:', error);
        if (isMounted) {
          navigate('/', { replace: true });
        }
      }
    };

    verifyAuth();

    return () => {
      isMounted = false;
    };
  }, [loading, checkAuthStatus, navigate, currentUser]);

  // 認証チェック中またはチェックが完了していない場合はローディング画面を表示
  if (loading || !authChecked) {
    return <PageLoader message="認証状態を確認中..." />;
  }

  // 認証済みの場合のみ子コンポーネントを表示
  return <>{children}</>;
}