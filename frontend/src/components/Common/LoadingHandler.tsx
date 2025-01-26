import { useAuth } from '../../contexts/AuthContext';

interface LoadingHandlerProps {
  children: React.ReactNode;
}

export default function LoadingHandler({ children }: LoadingHandlerProps) {
  const { loading } = useAuth();

  if (loading) {
    return null; // またはローディングUI
  }

  return <>{children}</>;
}
