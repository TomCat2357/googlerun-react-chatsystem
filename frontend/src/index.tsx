import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import ProtectedRoute from "./routing/ProtectedRoute";
import LoginPage from "./components/Login/LoginPage";
import MainPage from "./components/Main/MainPage";
import ChatPage from "./components/Chat/ChatPage";
import Header from "./components/Header/Header";
import "./index.css";
import GeocodingPage from "./components/Geocoding/GeocodingPage";

function App() {
  return (
    <Router>
      <AuthProvider>
        <div className="min-h-screen bg-dark-primary">
          <Routes>
            {/* ログインページ - ヘッダーなし */}
            <Route path="/" element={<LoginPage />} />

            {/* 認証が必要なルート - ヘッダーあり */}
            <Route
              path="/app/*"
              element={
                <ProtectedRoute>
                  <>
                    <Header />
                    <Routes>
                      <Route path="main" element={<MainPage />} />
                      <Route path="chat" element={<ChatPage />} />
                      <Route path="geocoding" element={<GeocodingPage />} />
                    </Routes>
                  </>
                </ProtectedRoute>
              }
            />

            {/* 無効なパスのリダイレクト */}
            <Route path="*" element={<Navigate to="/app/main" replace />} />
          </Routes>
        </div>
      </AuthProvider>
    </Router>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
