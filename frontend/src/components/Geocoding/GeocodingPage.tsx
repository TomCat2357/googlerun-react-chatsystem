// src/components/GeocodingInput.tsx
import React, { useState } from "react";

const GeocodingPage = () => {
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputText(text);

    // 改行で分割し、空行（スペースのみの行を含む）を除外してカウント
    const validLines = text
      .split("\n")
      .filter((line) => line.trim().length > 0);

    setLineCount(validLines.length);
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
札幌市北区北２３条西４丁目３－４"/>
      </div>
      <div className="text-right">
        <span className="text-sm text-gray-200">
          有効な行数: <strong>{lineCount}</strong>
        </span>
      </div>
    </div>
  );
};
export default GeocodingPage;
