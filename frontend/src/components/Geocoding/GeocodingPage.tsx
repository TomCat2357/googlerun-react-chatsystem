// src/components/GeocodingInput.tsx
import React, { useState } from "react";

const GeocodingPage = () => {
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [isSending, setIsSending] = useState(false);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputText(text);

    // 改行で分割し、空行（スペースのみの行を含む）を除外してカウント
    const validLines = text
      .split("\n")
      .filter((line) => line.trim().length > 0);

    setLineCount(validLines.length);
  };

  const handleSendLines = async () => {
    // 改行で分割して、空行 (スペースのみの行も除外) を配列にする
    const validLines = inputText
      .split("\n")
      .filter((line) => line.trim().length > 0);
    setIsSending(true);
    try {
      const response = await fetch("/backend/query2coordinates", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // 認証トークンがあれば以下のように追加します
          // "Authorization": "Bearer <your_token_here>"
        },
        body: JSON.stringify({ lines: validLines }),
      });
      if (!response.ok) {
        throw new Error("サーバーからエラーが返されました");
      }
      const data = await response.json();
      console.log("送信成功", data);
    } catch (error) {
      console.error("送信エラー", error);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-gray-100">
        住所ジオコーディング
      </h1>
      <div className="mb-4">
        <label
          htmlFor="addressInput"
          className="block text-sm font-medium mb-2 text-gray-200"
        >
          住所一覧（1行に1つの住所を入力）
        </label>
        <textarea
          id="addressInput"
          value={inputText}
          onChange={handleTextChange}
          className="w-full h-64 p-2 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg 
                     focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="札幌市役所　札幌市中央区北１条西２丁目
札幌市北区北２３条西４丁目３－４"
        />
      </div>
      <div className="flex justify-between items-center">
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
    </div>
  );
};

export default GeocodingPage;
