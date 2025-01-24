// src/components/Login/LoginPage.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';  // 変更点1
import { getAuth, signInWithPopup, GoogleAuthProvider } from 'firebase/auth';
import { app } from '../../firebase/firebase'; // Import the Firebase app instance

export default function LoginPage() {
  const [error, setError] = useState<string>('');
  const navigate = useNavigate();
  const { setCurrentUser } = useAuth();  // 変更点2
  const onLoginSuccess = (user) => {
    setCurrentUser(user);
    navigate('/app/main');
  };

  const handleLogin = async () => {
    try {
      const auth = getAuth(app); // Use the imported Firebase app instance
      const provider = new GoogleAuthProvider();
      const result = await signInWithPopup(auth, provider);
      
      console.log('Logged in user:', result.user.email);
      onLoginSuccess(result.user);
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