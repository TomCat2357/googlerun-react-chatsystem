import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, getAuth, onAuthStateChanged } from 'firebase/auth';
import axios from 'axios';

// 認証コンテキストの型定義
interface AuthContextType {
  currentUser: User | null;  // 現在のユーザー情報
  setCurrentUser: (user: User | null) => void;  // ユーザー情報を更新する関数
  checkAuthStatus: () => Promise<boolean>;  // 認証状態を確認する関数
}

// 認証コンテキストの作成
const AuthContext = createContext<AuthContextType | null>(null);

// 認証プロバイダーコンポーネント
export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const auth = getAuth();

  // Firebaseの認証状態変更を監視
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (user) {
        // ユーザーがログインしている場合
        const token = await user.getIdToken();
        localStorage.setItem('firebaseToken', token);  // トークンをローカルストレージに保存
        setCurrentUser(user);
      } else {
        // ユーザーがログアウトしている場合
        localStorage.removeItem('firebaseToken');
        setCurrentUser(null);
      }
    });

    // クリーンアップ関数
    return () => unsubscribe();
  }, []);

  // バックエンドとの認証状態の検証
  const checkAuthStatus = async () => {
    try {
      console.log('checkAuthStatus called');
      if (!auth.currentUser) {
        console.log('Current auth state:', auth);
        console.log('Current user state:', currentUser);
        return false;
      }
      // 最新のトークンを取得
      const token = await auth.currentUser.getIdToken(true);
      console.log('Token obtained:', token.substring(0, 10) + '...');
      
      // バックエンドへ認証確認リクエスト
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
      console.error('Auth check error:', {
        name: error.name,
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      return false;
    }
  };

  // コンテキストで提供する値
  const value = {
    currentUser,
    setCurrentUser,
    checkAuthStatus,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// カスタムフック - 認証コンテキストを使用するためのヘルパー
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}