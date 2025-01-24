// src/components/Login/LoginPage.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { initializeApp } from 'firebase/app';
import { getAuth, signInWithPopup, GoogleAuthProvider } from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN
};

// Firebaseの初期化
initializeApp(firebaseConfig);

// exportの方法を修正
export default function LoginPage() {  // defaultエクスポートに変更
  const [error, setError] = useState<string>('');
  const navigate = useNavigate();
  
  const handleLogin = async () => {
    try {
      const auth = getAuth();
      const provider = new GoogleAuthProvider();
      const result = await signInWithPopup(auth, provider);
      
      console.log('Logged in user:', result.user.email);
      navigate('/main');
    } catch (err) {
      setError('ログインに失敗しました');
      console.error('Login error:', err);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <div>
        <h1>ログイン</h1>
        {error && <p style={{ color: 'red' }}>{error}</p>}
        <button onClick={handleLogin}>
          Googleでログイン
        </button>
      </div>
    </div>
  );
}