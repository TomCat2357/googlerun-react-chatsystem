// frontend/src/components/SpeechToText/SpeechToTextPage.tsx

import React, { useState, useRef } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import Encoding from "encoding-japanese";

const SpeechToTextPage = () => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // アップロード方法の選択状態："file" または "base64"
  const [uploadMode, setUploadMode] = useState<"file" | "base64">("file");

  // ファイル選択とBase64貼り付け用の状態（どちらか片方のみ利用）
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");

  // 送信に使用する音声データ（ファイル選択優先）
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);

  // バックエンドから返却された文字起こし結果
  const [outputText, setOutputText] = useState("");

  // ファイル入力要素をリセットするためのref
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ファイルの読み込み処理（FileReader）
  const processFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result as string;
      setFileBase64Data(result);
      // ファイル選択時はBase64貼り付け状態をクリア
      setPastedBase64Data("");
    };
    reader.readAsDataURL(file);
  };

  // ファイル選択時のハンドラー
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
  };

  // ドラッグ＆ドロップ時のハンドラー
  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    processFile(file);
  };

  // Base64貼り付け時のハンドラー
  const handleTextInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setPastedBase64Data(value);
    // 貼り付け時はファイル選択状態をクリア
    setFileBase64Data("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // ヘッダーの「クリア」ボタン押下時の処理（全ての入力・結果をリセット）
  const handleClearBoth = () => {
    setFileBase64Data("");
    setPastedBase64Data("");
    setOutputText("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // 送信ボタン押下時の処理
  const handleSend = async () => {
    try {
      if (!audioData) {
        alert("送信するデータがありません");
        return;
      }
      const response = await fetch(`${API_BASE_URL}/backend/speech2text`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ audio_data: audioData }),
      });
      if (response.ok) {
        const data = await response.json();
        setOutputText(data.transcription);
      } else {
        setOutputText("エラーが発生しました");
      }
    } catch (error) {
      console.error(error);
      setOutputText("エラーが発生しました");
    }
  };

  // ダウンロード時のエンコーディング選択（"utf8"または"shift-jis"）の状態
  const [selectedEncoding, setSelectedEncoding] = useState("utf8");

  // ダウンロードボタン押下時の処理
  const handleDownload = () => {
    let blob;
    let filename = "transcription.txt";
    if (selectedEncoding === "utf8") {
      blob = new Blob([outputText], { type: "text/plain;charset=utf-8" });
    } else {
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
        {/* ヘッダー：タイトルと右側にクリアボタン */}
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">音声文字起こし</h1>
          <button
            onClick={handleClearBoth}
            className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
          >
            クリア
          </button>
        </div>

        {/* アップロードセクション */}
        <div className="mb-6">
          <h2 className="text-xl font-bold mb-2">音声アップロード</h2>
          {/* ① アップロード方法選択のラジオボタン */}
          <div className="mb-4">
            <div>
              <label className="mr-4 text-gray-200">
                <input
                  type="radio"
                  name="uploadMode"
                  value="file"
                  checked={uploadMode === "file"}
                  onChange={() => setUploadMode("file")}
                />{" "}
                ファイル選択
              </label>
              <label className="text-gray-200">
                <input
                  type="radio"
                  name="uploadMode"
                  value="base64"
                  checked={uploadMode === "base64"}
                  onChange={() => setUploadMode("base64")}
                />{" "}
                Base64貼り付け
              </label>
            </div>
          </div>

          {/* ② 選択されたアップロード方法に応じた入力欄 */}
          {uploadMode === "file" ? (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              className="border-dashed border-2 border-gray-400 p-4 mb-4 text-center cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              ここにドラッグ＆ドロップするか、クリックしてファイルを選択してください（音声ファイル）
              <input
                type="file"
                ref={fileInputRef}
                accept="audio/*"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>
          ) : (
            <div className="mb-4">
              <label className="block mb-2">Base64エンコードされたデータを貼り付け</label>
              <textarea
                placeholder="Base64データを貼り付けてください"
                onChange={handleTextInputChange}
                value={pastedBase64Data}
                className="w-full p-2 text-black"
                rows={4}
              />
            </div>
          )}

          {/* アップロードされたデータの先頭部分を表示 */}
          <div className="mb-4">
            <p className="text-sm">
              アップロードされたデータ: <span className="text-green-300">{preview}</span>
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

        {/* ダウンロードボタンとエンコーディング選択ラジオボタンを同一行に配置 */}
        <div className="mt-6 flex items-center space-x-4">
          <button
            onClick={handleDownload}
            className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded"
          >
            ダウンロード
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
      </div>
    </div>
  );
};

export default SpeechToTextPage;
