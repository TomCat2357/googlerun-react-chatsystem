import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * ページレベルでの認証ガード用カスタムフック
 * @returns authReady - 認証チェックが完了したかどうか
 */
export function useAuthGuard(): boolean {
  const [authReady, setAuthReady] = useState(false);
  const { currentUser, checkAuthStatus, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    let isMounted = true;

    const verifyAuth = async () => {
      // 認証確認中はまだチェックしない
      if (loading) return;

      try {
        const isAuthenticated = await checkAuthStatus();
        
        // コンポーネントがアンマウントされていないか確認
        if (!isMounted) return;
        
        if (!isAuthenticated) {
          // 認証されていない場合はログインページにリダイレクト
          navigate('/', { replace: true });
        } else {
          // 認証が確認できたのでUIを表示可能
          setAuthReady(true);
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

  return authReady;
}