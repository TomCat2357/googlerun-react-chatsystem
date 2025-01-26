// src/components/Login/LoginPage.tsx
import LoginButton from '../Auth/LoginButton';

export default function LoginPage() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <div>
        <h1>ログイン</h1>
        <LoginButton />
      </div>
    </div>
  );
}