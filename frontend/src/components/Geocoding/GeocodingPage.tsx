// geocodingpage.tsx
import React, { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";

const GeocodingPage = () => {
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const [token, setToken] = useState<string>("");
  const [results, setResults] = useState<
    Array<{ address: string; latitude: number | null; longitude: number | null; error?: string }>
  >([]);

  const { currentUser } = useAuth();
  const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL;

  useEffect(() => {
    if (currentUser) {
      currentUser
        .getIdToken()
        .then((t) => setToken(t))
        .catch((err) => console.error("トークン取得エラー:", err));
    }
  }, [currentUser]);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputText(text);
    const validLines = text.split("\n").filter((line) => line.trim().length > 0);
    setLineCount(validLines.length);
  };

  // 各行を送信してジオコーディングを実行する処理
  const handleSendLines = async () => {
    const validLines = inputText.split("\n").filter((line) => line.trim().length > 0);
    if (validLines.length === 0) return;

    const confirmed = window.confirm(`${validLines.length} 行です。実行しますか？`);
    if (!confirmed) return;

    setIsSending(true);
    try {
      const response = await fetch(`${API_BASE_URL}/backend/query2coordinates`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ lines: validLines }),
      });
      if (!response.ok) {
        throw new Error("サーバーからエラーが返されました");
      }
      const data = await response.json();
      console.log("送信成功", data);
      setResults(data.results || []);
    } catch (error) {
      console.error("送信エラー", error);
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Shift+Enterの場合は改行を許可
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendLines();
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-gray-100">住所ジオコーディング</h1>
      <div className="mb-4">
        <label htmlFor="addressInput" className="block text-sm font-medium mb-2 text-gray-200">
          住所一覧（1行に1つの住所を入力）
        </label>
        <textarea
          id="addressInput"
          value={inputText}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          className="w-full h-64 p-2 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="例: 札幌市役所　札幌市中央区北１条西２丁目&#10;札幌市北区北２３条西４丁目３－４"
        />
      </div>
      <div className="flex justify-between items-center mb-4">
        <span className="text-sm text-gray-200">
          有効な行数: <strong>{lineCount}</strong>
        </span>
        <button
          onClick={handleSendLines}
          disabled={isSending}
          className="px-4 py-2 bg-blue-600 text-gray-100 rounded hover:bg-blue-500 transition"
        >
          {isSending ? "送信中..." : "行を送信"}
        </button>
      </div>
      <div>
        <h2 className="text-xl font-bold mb-2 text-gray-100">ジオコーディング結果</h2>
        {results.length === 0 ? (
          <p className="text-gray-200">結果がまだありません。</p>
        ) : (
          <ul className="text-gray-200">
            {results.map((result, index) => (
              <li key={index} className="mb-2 border-b border-gray-700 pb-2">
                <p>
                  <strong>住所:</strong> {result.address}
                </p>
                {result.latitude !== null && result.longitude !== null ? (
                  <p>
                    <strong>緯度:</strong> {result.latitude}　<strong>経度:</strong> {result.longitude}
                  </p>
                ) : (
                  <p className="text-red-400">ジオコーディングに失敗しました: {result.error}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default GeocodingPage;
