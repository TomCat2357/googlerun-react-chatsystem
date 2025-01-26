import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { getAuth, signInWithPopup, GoogleAuthProvider } from 'firebase/auth';
import { app } from '../../firebase/firebase';

export default function LoginButton() {
  const [error, setError] = useState<string>('');
  const navigate = useNavigate();
  const { setCurrentUser } = useAuth();

  const onLoginSuccess = (user) => {
    setCurrentUser(user);
    navigate('/app/main');
  };

  const handleLogin = async () => {
    try {
      const auth = getAuth(app);
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
    <>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <button onClick={handleLogin}>
        Googleでログイン
      </button>
    </>
  );
}
