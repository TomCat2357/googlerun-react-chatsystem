// frontend/src/components/SpeechToText/SpeechToTextPage.tsx

import React, { useState, useRef } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import Encoding from "encoding-japanese";

interface AudioInfo {
  duration: number;
  fileName?: string;
  fileSize?: number | null;
  mimeType?: string;
}

const SpeechToTextPage = () => {
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // アップロード方法の選択："file"（ファイル選択／ドラッグ＆ドロップ） or "base64"
  const [uploadMode, setUploadMode] = useState<"file" | "base64">("file");

  // ファイル選択用とBase64貼り付け用のデータ（どちらか片方のみ有効）
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);

  // バックエンドからの文字起こし結果
  const [outputText, setOutputText] = useState("");

  // 音声データのメタ情報（再生時間、ファイル名、サイズ、MIMEタイプ）
  const [audioInfo, setAudioInfo] = useState<AudioInfo | null>(null);

  // ファイル入力要素の参照（リセット用）
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ファイル選択／ドラッグ時の処理
  const processFile = (file: File) => {
    // ① 音声ファイルかどうかチェック
    if (!file.type.startsWith("audio/")) {
      alert("音声ファイル以外はアップロードできません");
      return;
    }
    // Audioオブジェクトでメタ情報を取得
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.src = url;
    audio.onloadedmetadata = () => {
      setAudioInfo({
        duration: audio.duration,
        fileName: file.name,
        fileSize: file.size,
        mimeType: file.type,
      });
      URL.revokeObjectURL(url);
    };
    audio.onerror = () => {
      alert("無効な音声データです");
      setFileBase64Data("");
      setAudioInfo(null);
      URL.revokeObjectURL(url);
    };

    // FileReaderでBase64文字列に変換
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result as string;
      setFileBase64Data(result);
      setPastedBase64Data("");
    };
    reader.readAsDataURL(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
  };

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    processFile(file);
  };

  // Base64貼り付けの場合の入力文字列チェック用関数
  const isValidBase64String = (str: string): boolean => {
    // 余分な空白を除去
    const cleaned = str.replace(/\s/g, "");
    if (cleaned === "") return false;
    // data URL形式の場合は、カンマ以降の部分だけチェック
    if (cleaned.startsWith("data:")) {
      const parts = cleaned.split(",");
      if (parts.length < 2) return false;
      const base64Part = parts[1];
      return /^[A-Za-z0-9+/=]+$/.test(base64Part);
    } else {
      return /^[A-Za-z0-9+/=]+$/.test(cleaned);
    }
  };

  // Base64貼り付けデータの処理（メタ情報取得）
  const processBase64Data = (data: string) => {
    let dataUrl = data;
    const cleaned = data.replace(/\s/g, "");
    if (!isValidBase64String(cleaned)) {
      alert("無効なBase64データです");
      setPastedBase64Data("");
      setAudioInfo(null);
      return;
    }
    // rawなBase64の場合は、デフォルトのMIMEタイプを付与
    if (!cleaned.startsWith("data:")) {
      dataUrl = "data:audio/mpeg;base64," + cleaned;
    }
    // Audioオブジェクトでメタ情報を取得
    const audio = new Audio();
    audio.src = dataUrl;
    audio.onloadedmetadata = () => {
      setAudioInfo({
        duration: audio.duration,
        fileName: "Base64貼り付けデータ",
        fileSize: null, // サイズは不明
        mimeType: audio.src.substring(5, audio.src.indexOf(";")),
      });
    };
    audio.onerror = () => {
      alert("無効な音声データです");
      setPastedBase64Data("");
      setAudioInfo(null);
    };
    setPastedBase64Data(dataUrl);
  };

  const handleTextInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    // Base64貼り付け時はファイル選択をクリア
    setFileBase64Data("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setPastedBase64Data(value);
    if (value.trim() !== "") {
      processBase64Data(value);
    } else {
      setAudioInfo(null);
    }
  };

  // ヘッダーの「クリア」ボタン：全ての入力・結果・メタ情報をリセット
  const handleClearBoth = () => {
    setFileBase64Data("");
    setPastedBase64Data("");
    setOutputText("");
    setAudioInfo(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

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

  const [selectedEncoding, setSelectedEncoding] = useState("utf8");
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
          <h2 className="text-xl font-bold mb-2">音声データのアップロード方法</h2>
          {/* アップロード方法選択 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-200 mb-2">アップロード方法</label>
            <div>
              <label className="mr-4 text-gray-200">
                <input
                  type="radio"
                  name="uploadMode"
                  value="file"
                  checked={uploadMode === "file"}
                  onChange={() => {
                    setUploadMode("file");
                    handleClearBoth();
                  }}
                />{" "}
                ファイル選択
              </label>
              <label className="text-gray-200">
                <input
                  type="radio"
                  name="uploadMode"
                  value="base64"
                  checked={uploadMode === "base64"}
                  onChange={() => {
                    setUploadMode("base64");
                    handleClearBoth();
                  }}
                />{" "}
                Base64貼り付け
              </label>
            </div>
          </div>

          {/* 選択されたアップロード方法に応じた入力欄 */}
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

          {/* プレビュー表示 */}
          <div className="mb-4">
            <p className="text-sm">
              アップロードされたデータの先頭: <span className="text-green-300">{preview}</span>
            </p>
          </div>

          {/* 音声情報の表示 */}
          {audioInfo && (
            <div className="mb-4">
              <p className="text-sm">
                音声情報:{" "}
                {audioInfo.fileName && `ファイル名: ${audioInfo.fileName}, `}
                {audioInfo.duration !== undefined && `再生時間: ${audioInfo.duration.toFixed(2)}秒, `}
                {audioInfo.fileSize !== null && audioInfo.fileSize !== undefined && `ファイルサイズ: ${(audioInfo.fileSize / 1024).toFixed(1)}KB, `}
                {audioInfo.mimeType && `MIMEタイプ: ${audioInfo.mimeType}`}
              </p>
            </div>
          )}
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

        {/* ダウンロードボタンとエンコーディング選択 */}
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
