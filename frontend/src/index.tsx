// frontend/src/index.tsx を修正
import React, { StrictMode, Suspense } from "react";
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
import Header from "./components/Header/Header";
import "./index.css";
import * as Config from "./config";  // 追加

// 遅延ロードするコンポーネント
const ChatPage = React.lazy(() => import("./components/Chat/ChatPage"));
const GeocodingPage = React.lazy(
  () => import("./components/Geocoding/GeocodingPage")
);
const SpeechToTextPage = React.lazy(
  () => import("./components/SpeechToText/SpeechToTextPage")
);
const GenerateImagePage = React.lazy(
  () => import("./components/GenerateImage/GenerateImagePage")
);

// ローディング表示用コンポーネント
const LoadingFallback = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
  </div>
);

function App() {
  return (
    <Router>
      <AuthProvider>
        <div className="min-h-screen bg-dark-primary">
          <Routes>
            <Route path="/" element={<LoginPage />} />

            <Route
              path="/app/*"
              element={
                <ProtectedRoute>
                  <>
                    <Header />
                    <Suspense fallback={<LoadingFallback />}>
                      <Routes>
                        <Route path="main" element={<MainPage />} />
                        <Route path="chat" element={<ChatPage />} />
                        <Route path="geocoding" element={<GeocodingPage />} />
                        <Route
                          path="speechtotext"
                          element={<SpeechToTextPage />}
                        />
                        <Route
                          path="generate-image"
                          element={<GenerateImagePage />}
                        />
                      </Routes>
                    </Suspense>
                  </>
                </ProtectedRoute>
              }
            />

            <Route path="*" element={<Navigate to={Config.getClientPath("/app/main")} replace />} />
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