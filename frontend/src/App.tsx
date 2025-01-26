// src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainPage from './components/Main/MainPage';
import LoginPage from './components/Login/LoginPage';
import ProtectedRoute from './routing/ProtectedRoute';
import { AuthProvider } from './contexts/AuthContext';
import LoadingHandler from './components/Common/LoadingHandler';
import ChatContainer from './components/Chat/ChatContainer';  // 追加

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <LoadingHandler>
          <Routes>
            <Route path="/" element={<LoginPage />} />
            <Route path="/app/chat" element={<ChatContainer />} /> {/* 追加：認証なしでアクセス可能 */}
            <Route
              path="/app/main"
              element={
                <ProtectedRoute>
                  <MainPage />
                </ProtectedRoute>
              }
            />
          </Routes>
        </LoadingHandler>
      </BrowserRouter>
    </AuthProvider>
  );
}