// frontend/src/components/SpeechToText/SpeechToTextPage.tsx

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import Encoding from "encoding-japanese";

const SpeechToTextPage = () => {
  const navigate = useNavigate();
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // アップロードされた音声データ（base64文字列）
  const [base64Data, setBase64Data] = useState("");
  // アップロードされたデータの先頭部分（プレビュー用）
  const [preview, setPreview] = useState("");
  // バックエンドから返却された文字起こし結果
  const [outputText, setOutputText] = useState("");
  // ダウンロード時のエンコーディング選択（"utf8"または"shift-jis"）
  const [selectedEncoding, setSelectedEncoding] = useState("utf8");

  // ① ローカルファイルからアップロード時の処理
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result as string;
      setBase64Data(result);
      // 先頭30文字をプレビューとして表示
      setPreview(result.substring(0, 30));
    };
    // "data:audio/～;base64,..."形式で読み込み
    reader.readAsDataURL(file);
  };

  // ② テキストボックスにbase64エンコード済みの文字列を貼り付けた場合の処理
  const handleTextInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setBase64Data(value);
    setPreview(value.substring(0, 30));
  };

  // 送信ボタン押下時：バックエンドのエンドポイントへPOSTリクエストを送信
  const handleSend = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/backend/speech2text`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ audio_data: base64Data }),
      });
      if (response.ok) {
        const data = await response.json();
        // backend側で"transcription"フィールドに結果を返す前提
        setOutputText(data.transcription);
      } else {
        setOutputText("エラーが発生しました");
      }
    } catch (error) {
      console.error(error);
      setOutputText("エラーが発生しました");
    }
  };

  // ダウンロードボタン押下時：文字起こし結果を選択されたエンコーディングでテキストファイルとしてダウンロード
  const handleDownload = () => {
    let blob;
    let filename = "transcription.txt";
    if (selectedEncoding === "utf8") {
      blob = new Blob([outputText], { type: "text/plain;charset=utf-8" });
    } else {
      // Shift-JISに変換
      const sjisArray = Encoding.convert(outputText, { to: "SJIS", type: "array" });
      blob = new Blob([new Uint8Array(sjisArray)], { type: "text/plain;charset=shift_jis" });
      filename = "transcription_sjis.txt";
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

  return (
    <div className="min-h-screen bg-dark-primary text-white">
      <div className="container mx-auto px-4 py-8">
        {/* ヘッダー＋戻るボタン */}
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">音声文字起こし</h1>
          <button
            onClick={() => navigate("/app/main")}
            className="bg-gray-600 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded"
          >
            戻る
          </button>
        </div>

        {/* アップロードセクション */}
        <div className="mb-6">
          <h2 className="text-xl font-bold mb-2">音声データのアップロード方法</h2>
          {/* ① ローカルファイルからアップロード */}
          <div className="mb-4">
            <label className="block mb-2">ローカルファイルからアップロード</label>
            <input
              type="file"
              accept="audio/*"
              onChange={handleFileChange}
              className="block w-full text-gray-700"
            />
          </div>
          {/* ② Base64エンコード済み文字列の貼り付け */}
          <div className="mb-4">
            <label className="block mb-2">Base64エンコードされたデータを貼り付け</label>
            <textarea
              placeholder="Base64データを貼り付けてください"
              onChange={handleTextInputChange}
              className="w-full p-2 text-black"
              rows={4}
            />
          </div>
          {/* アップロードされたデータの先頭部分を表示 */}
          <div className="mb-4">
            <p className="text-sm">
              アップロードされたデータの先頭:{" "}
              <span className="text-green-300">{preview}</span>
            </p>
          </div>
        </div>

        {/* 送信ボタン */}
        <button
          onClick={handleSend}
          className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
        >
          送信
        </button>

        {/* 文字起こし結果の表示 */}
        <div className="mt-6">
          <h2 className="text-xl font-bold mb-2">文字起こし結果</h2>
          <textarea
            value={outputText}
            readOnly
            className="w-full p-2 text-black"
            rows={6}
          />
        </div>

        {/* テキストダウンロードセクション */}
        <div className="mt-6">
          <h2 className="text-xl font-bold mb-2">テキストのダウンロード</h2>
          <div className="flex items-center mb-4">
            <label className="mr-2">エンコーディング:</label>
            <select
              value={selectedEncoding}
              onChange={(e) => setSelectedEncoding(e.target.value)}
              className="text-black"
            >
              <option value="utf8">UTF-8</option>
              <option value="shift-jis">Shift-JIS</option>
            </select>
          </div>
          <button
            onClick={handleDownload}
            className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded"
          >
            ダウンロード
          </button>
        </div>
      </div>
    </div>
  );
};

export default SpeechToTextPage;
