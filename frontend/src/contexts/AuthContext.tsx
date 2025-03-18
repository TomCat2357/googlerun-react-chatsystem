import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, getAuth, onAuthStateChanged } from 'firebase/auth';


// interfaceの更新も必要
interface AuthContextType {
  currentUser: User | null;
  setCurrentUser: (user: User | null) => void;
  checkAuthStatus: () => Promise<boolean>;
  loading: boolean;
  refreshToken: () => Promise<string | null>;
  checkTokenExpiration: () => Promise<string | null>;
}

// 認証コンテキストの作成
const AuthContext = createContext<AuthContextType | null>(null);

// 認証プロバイダーコンポーネント
export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const auth = getAuth();

  // ここに定数とトークン関連の関数を追加
  const TOKEN_REFRESH_THRESHOLD = 10 * 60; // 10分前にリフレッシュ

  const refreshToken = async () => {
    console.log('refreshToken関数が呼び出されました');
    if (auth.currentUser) {
      console.log('現在のユーザーが存在します。トークンをリフレッシュします。');
      const token = await auth.currentUser.getIdToken(true);
      console.log('新しいトークンを取得しました:', token.substring(0, 10) + '...');
      return token;
    }
    console.log('現在のユーザーが存在しないため、トークンをリフレッシュできません');
    return null;
  };

  const base64Decode = (str: string): string => {
    // Base64URLをBase64に変換
    const base64 = str.replace(/-/g, '+').replace(/_/g, '/');
    // パディングを追加
    const pad = base64.length % 4;
    if (pad) {
      return base64 + '='.repeat(4 - pad);
    }
    return base64;
  };

  const checkTokenExpiration = async () => {
    console.log('checkTokenExpiration関数が呼び出されました');
    if (auth.currentUser) {
      console.log('現在のユーザーが存在します。トークンの有効期限を確認します。');
      const token = await auth.currentUser.getIdToken();
      const payload = token.split('.')[1];
      const decodedToken = JSON.parse(atob(base64Decode(payload)));
      const expirationTime = decodedToken.exp;
      const currentTime = Math.floor(Date.now() / 1000);
      console.log(`トークンの有効期限: ${expirationTime}, 現在の時刻: ${currentTime}, リフレッシュまで: ${expirationTime - currentTime - TOKEN_REFRESH_THRESHOLD}秒`);

      if (expirationTime - currentTime < TOKEN_REFRESH_THRESHOLD) {
        console.log('トークンの有効期限が閾値を下回ったため、トークンをリフレッシュします');
        const newToken = await refreshToken();
        if (newToken) {
          console.log('トークンを正常にリフレッシュしました');
        } else {
          console.log('トークンのリフレッシュに失敗しました');
        }
        return newToken;
      } else {
        console.log('トークンの有効期限は十分です');
      }
    } else {
      console.log('現在のユーザーが存在しないため、トークンの有効期限を確認できません');
    }
    return null;
  };

  // Firebaseの認証状態変更を監視
  useEffect(() => {
    console.log('AuthProviderのuseEffectが実行されました');
    // ユーザーの認証状態が変化した際に呼び出される
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      console.log('onAuthStateChangedが呼び出されました。ユーザー情報:', user);
      if (user) {
        // ユーザーがログインしている場合
        console.log('ユーザーがログインしています。トークンを取得します。');
        const token = await user.getIdToken();
        console.log('Firebaseトークンを取得:', token.substring(0, 10) + '...');
        setCurrentUser(user);
        console.log('currentUserが更新されました:', user);
      } else {
        // ユーザーがログアウトしている場合
        console.log('ユーザーがログアウトまたは未ログインの状態です');
        setCurrentUser(null);
        console.log('currentUserがnullに設定されました');
      }
      setLoading(false); // データの読み込みが完了
      console.log('Loadingステートがfalseに設定されました');
    });

    // コンポーネントのアンマウント時にリスナーを解除
    return () => {
      console.log('onAuthStateChangedリスナーを解除します');
      unsubscribe();
    };
  }, [auth]);

  // トークンリフレッシュ監視のuseEffect
  useEffect(() => {
    console.log('トークンリフレッシュ用のuseEffectが実行されました');
    const tokenRefreshInterval = setInterval(async () => {
      console.log('トークン有効期限チェックを実行します');
      const newToken = await checkTokenExpiration();
      if (newToken) {
        console.log('トークンが更新されました:', newToken.substring(0, 10) + '...');
      } else {
        console.log('トークンの更新は不要または失敗しました');
      }
    }, 60000);

    return () => {
      console.log('トークンチェックインターバルをクリアします');
      clearInterval(tokenRefreshInterval);
    };
  }, []);

  // バックエンドとの認証状態の検証
  const checkAuthStatus = async () => {
    console.log('checkAuthStatus関数が呼び出されました');
    try {
      // Firebaseの認証状態のみをチェック
      const isAuthenticated = !!auth.currentUser;
      console.log('認証状態（Firebase側のみ）:', isAuthenticated);
      return isAuthenticated;

    } catch (error: any) {
      console.error('認証チェック中にエラーが発生しました:', {
        name: error.name,
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      return false;
    }
  };

  // コンテキストで提供する値
  const value: AuthContextType = {
    currentUser,
    setCurrentUser,
    checkAuthStatus,
    loading,
    refreshToken,
    checkTokenExpiration
  };

  console.log('AuthProviderがレンダリングされました。提供する値:', value);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// カスタムフック - 認証コンテキストを使用するためのヘルパー
export function useAuth() {
  console.log('useAuthフックが呼び出されました');
  const context = useContext(AuthContext);
  if (!context) {
    console.error('useAuthはAuthProvider内でのみ使用可能です');
    throw new Error('useAuthはAuthProvider内でのみ使用可能です');
  }
  console.log('useAuthフックからコンテキストを取得:', context);
  return context;
}