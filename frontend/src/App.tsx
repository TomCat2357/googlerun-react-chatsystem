// src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainPage from './components/Main/MainPage';
import LoginPage from './components/Login/LoginPage';
import ProtectedRoute from './routing/ProtectedRoute';
import { AuthProvider } from './contexts/AuthContext';  // 追加

export default function App() {
  return (
    <AuthProvider>      {/* AuthProvider を追加 */}
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route
            path="/app/main"
            element={
              <ProtectedRoute>
                <MainPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}