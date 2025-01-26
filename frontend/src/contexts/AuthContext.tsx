import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, getAuth, onAuthStateChanged } from 'firebase/auth';
import axios from 'axios';

// 認証コンテキストの型定義
interface AuthContextType {
  currentUser: User | null;  // 現在のユーザー情報
  setCurrentUser: (user: User | null) => void;  // ユーザー情報を更新する関数
  checkAuthStatus: () => Promise<boolean>;  // 認証状態を確認する関数
  loading: boolean; // 追加: 認証情報を読み込み中かどうかを示すフラグ
}

// 認証コンテキストの作成
const AuthContext = createContext<AuthContextType | null>(null);

// 認証プロバイダーコンポーネント
export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true); // 追加
  const auth = getAuth();

  // Firebaseの認証状態変更を監視
  useEffect(() => {
    // ユーザーの認証状態が変化した際に呼び出される
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      console.log('onAuthStateChangedが呼び出されました。ユーザー情報:', user);
      if (user) {
        // ユーザーがログインしている場合
        const token = await user.getIdToken();
        console.log('Firebaseトークンを取得:', token.substring(0, 10) + '...');
        setCurrentUser(user);
      } else {
        // ユーザーがログアウトしている場合
        console.log('ログアウトまたは未ログインの状態です');
        setCurrentUser(null);
      }
      setLoading(false); // データの読み込みが完了
      console.log('Loadingステートがfalseに設定されました');
    });

    // コンポーネントのアンマウント時にリスナーを解除
    return () => {
      console.log('onAuthStateChangedリスナーを解除します');
      unsubscribe();
    };
  }, []);

  // バックエンドとの認証状態の検証
  const checkAuthStatus = async () => {
    try {
      console.log('checkAuthStatus called');
      if (!auth.currentUser) {
        console.log('ログイン中のユーザーが存在しません');
        console.log('Authオブジェクトの状態:', auth);
        console.log('currentUserの状態:', currentUser);
        return false;
      }
      // 最新のトークンを取得
      const token = await auth.currentUser.getIdToken(false);
      console.log('取得した最新トークン(先頭10文字):', token.substring(0, 10) + '...');
      
      // バックエンドへ認証確認リクエスト
      console.log('バックエンドへ認証確認のリクエストを送信します...');
      const response = await axios.get('http://localhost:8080/app/verify-auth', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      console.log('バックエンドからのレスポンス:', response.data);
      return response.data.status === 'success';
    } catch (error: any) {
      console.error('認証チェック中にエラーが発生:', {
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
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// カスタムフック - 認証コンテキストを使用するためのヘルパー
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuthはAuthProvider内でのみ使用可能です');
  }
  return context;
}