import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import PageLoader from '../utils/PageLoader';
import * as Config from "../config";

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { currentUser, loading } = useAuth();
  const navigate = useNavigate();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const verifyAuth = async () => {
      if (loading) return;

      if (!isMounted) return;

      // ユーザーがログインしているかクライアントサイドでチェック
      if (!currentUser) {
        console.log('未認証のためログインページにリダイレクト');
        navigate(Config.getClientPath('/'), { replace: true });
      } else {
        console.log('クライアントサイドでの認証確認成功');
        setAuthChecked(true);
      }
    };

    verifyAuth();

    return () => {
      isMounted = false;
    };
  }, [loading, navigate, currentUser]);

  // 認証チェック中またはチェックが完了していない場合はローディング画面を表示
  if (loading || !authChecked) {
    return <PageLoader message="認証状態を確認中..." />;
  }

  // 認証済みの場合のみ子コンポーネントを表示
  return <>{children}</>;
}