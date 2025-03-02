// frontend/src/components/Main/MainPage.tsx

import { useNavigate } from "react-router-dom";
import { useAuthGuard } from "../../utils/useAuthGuard";
import PageLoader from "../../utils/PageLoader";

const MainPage = () => {
  const navigate = useNavigate();
  const authReady = useAuthGuard();

  if (!authReady) {
    return <PageLoader />;
  }


  return (
    <div className="min-h-screen bg-dark-primary">
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-white mb-8">ダッシュボード</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* チャットへのリンクカード */}
          <div
            onClick={() => navigate("/app/chat")}
            className="bg-dark-secondary p-6 rounded-lg shadow-lg cursor-pointer hover:bg-dark-accent transition-colors"
          >
            <h2 className="text-xl font-bold text-white mb-2">チャット</h2>
            <p className="text-gray-300">AIとの対話を開始する</p>
          </div>

          {/* Geocodingへのリンクカード（仮実装） */}
          <div
            onClick={() => navigate("/app/geocoding")}
            className="bg-dark-secondary p-6 rounded-lg shadow-lg cursor-pointer hover:bg-dark-accent transition-colors"
          >
            <h2 className="text-xl font-bold text-white mb-2">Geocoding</h2>
            <p className="text-gray-300">地図変換機能</p>
          </div>

          {/* SpeechToTextへのリンクカード */}
          <div
            onClick={() => navigate("/app/speechtotext")}
            className="bg-dark-secondary p-6 rounded-lg shadow-lg cursor-pointer hover:bg-dark-accent transition-colors"
          >
            <h2 className="text-xl font-bold text-white mb-2">
              音声文字起こし
            </h2>
            <p className="text-gray-300">音声データをテキストに変換する</p>
          </div>
          {/* 画像生成へのリンクカード */}
          <div
            onClick={() => navigate("/app/generate-image")}
            className="bg-dark-secondary p-6 rounded-lg shadow-lg cursor-pointer hover:bg-dark-accent transition-colors"
          >
            <h2 className="text-xl font-bold text-white mb-2">画像生成</h2>
            <p className="text-gray-300">AIによる画像生成</p>
          </div>
        </div>
      </main>
    </div>
  );
};

export default MainPage;
