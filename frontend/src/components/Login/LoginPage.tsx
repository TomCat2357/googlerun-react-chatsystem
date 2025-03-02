import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import LoginButton from '../Auth/LoginButton';
import PageLoader from '../../utils/PageLoader';

export default function LoginPage() {
  const { currentUser, checkAuthStatus, loading } = useAuth();
  const navigate = useNavigate();
  
  useEffect(() => {
    const checkAuth = async () => {
      if (loading) return;
      
      if (currentUser) {
        const isAuthenticated = await checkAuthStatus();
        if (isAuthenticated) {
          navigate('/app/main', { replace: true });
        }
      }
    };
    
    checkAuth();
  }, [currentUser, loading, checkAuthStatus, navigate]);
  
  if (loading) {
    return <PageLoader message="認証状態を確認中..." />;
  }

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex flex-col justify-center items-center">
      <div className="bg-[#141414] p-8 rounded-xl shadow-2xl border border-zinc-800">
        <h1 className="text-3xl font-bold text-zinc-100 mb-8 text-center">
          環境管理補助システム
        </h1>
        <LoginButton />
      </div>
    </div>
  );
}