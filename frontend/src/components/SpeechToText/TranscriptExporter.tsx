// frontend/src/components/SpeechToText/TranscriptExporter.tsx
import React, { useState } from "react";

interface TranscriptExporterProps {
  getTranscriptText: () => string;
}

const TranscriptExporter: React.FC<TranscriptExporterProps> = ({ getTranscriptText }) => {
  const [selectedEncoding, setSelectedEncoding] = useState("utf8");
  const [copied, setCopied] = useState(false);

  const handleDownload = async () => {
    const textContent = getTranscriptText();
    if (!textContent) {
      alert("テキストが空です");
      return;
    }

    let blob;
    let filename = "transcription.txt";

    if (selectedEncoding === "utf8") {
      blob = new Blob([textContent], { type: "text/plain;charset=utf-8" });
    } else {
      // Shift-JISエンコーディングのためにEncoding-japaneseライブラリが必要
      try {
        // 動的にエンコーディングライブラリをインポート
        const Encoding = await import("encoding-japanese");
        const sjisArray = Encoding.convert(textContent, {
          to: "SJIS",
          type: "array",
        });
        blob = new Blob([new Uint8Array(sjisArray)], {
          type: "text/plain;charset=shift_jis",
        });
        filename = "transcription_sjis.txt";
      } catch (error) {
        console.error("エンコーディングエラー:", error);
        alert("Shift-JISへの変換に失敗しました");
        return;
      }
    }

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  const handleCopyToClipboard = async () => {
    const textContent = getTranscriptText();
    try {
      await navigator.clipboard.writeText(textContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 1000);
    } catch (error) {
      console.error("コピーエラー:", error);
      alert("クリップボードへのコピーに失敗しました");
    }
  };

  return (
    <div className="flex items-center space-x-4">
      <button
        onClick={handleDownload}
        className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded"
      >
        ダウンロード
      </button>
      <button
        onClick={handleCopyToClipboard}
        className={`font-bold py-2 px-4 rounded transition-colors duration-300 ${
          copied ? "bg-white text-black" : "bg-gray-500 hover:bg-gray-600 text-white"
        }`}
      >
        {copied ? "コピー完了！" : "クリップボードにコピー"}
      </button>
      <div className="flex items-center space-x-2">
        <label className="text-gray-200">
          <input
            type="radio"
            name="encoding"
            value="utf8"
            checked={selectedEncoding === "utf8"}
            onChange={() => setSelectedEncoding("utf8")}
          />{" "}
          UTF-8
        </label>
        <label className="text-gray-200">
          <input
            type="radio"
            name="encoding"
            value="shift-jis"
            checked={selectedEncoding === "shift-jis"}
            onChange={() => setSelectedEncoding("shift-jis")}
          />{" "}
          Shift-JIS
        </label>
      </div>
    </div>
  );
};

export default TranscriptExporter;