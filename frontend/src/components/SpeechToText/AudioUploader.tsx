// frontend/src/components/SpeechToText/AudioUploader.tsx
import React, { useRef, useState } from "react";

export interface AudioInfo {
  duration: number;
  fileName?: string;
  fileSize?: number | null;
  mimeType?: string;
}

interface AudioUploaderProps {
  onAudioDataChange: (audioData: string) => void;
  onAudioInfoChange: (audioInfo: AudioInfo | null) => void;
  onDescriptionChange: (description: string) => void;
  onRecordingDateChange: (date: string) => void;
}

const AudioUploader: React.FC<AudioUploaderProps> = ({
  onAudioDataChange,
  onAudioInfoChange,
  onDescriptionChange,
  onRecordingDateChange,
}) => {
  const [uploadMode, setUploadMode] = useState<"file" | "base64">("file");
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);

  const formatDate = (timestamp: number): string => {
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = ("0" + (date.getMonth() + 1)).slice(-2);
    const day = ("0" + date.getDate()).slice(-2);
    return `${year}/${month}/${day}`;
  };

  const processFile = async (file: File) => {
    if (!file.type.startsWith("audio/")) {
      alert("音声ファイル以外はアップロードできません");
      return;
    }
    
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.src = url;
    
    audio.onloadedmetadata = () => {
      onAudioInfoChange({
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
      onAudioInfoChange(null);
      URL.revokeObjectURL(url);
    };

    const fileData = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          resolve(event.target.result as string);
        } else {
          reject(new Error("ファイル読み込みエラー"));
        }
      };
      reader.onerror = () => reject(new Error("ファイル読み込みエラー"));
      reader.readAsDataURL(file);
    });

    setFileBase64Data(fileData);
    setPastedBase64Data("");
    onAudioDataChange(fileData);
    onDescriptionChange(file.name);
    onRecordingDateChange(formatDate(file.lastModified));
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

  const isValidBase64String = (str: string): boolean => {
    const cleaned = str.replace(/\s/g, "");
    if (cleaned === "") return false;
    if (cleaned.startsWith("data:")) {
      const parts = cleaned.split(",");
      if (parts.length < 2) return false;
      return /^[A-Za-z0-9+/=]+$/.test(parts[1]);
    } else {
      return /^[A-Za-z0-9+/=]+$/.test(cleaned);
    }
  };

  const processBase64Data = (data: string) => {
    let dataUrl = data;
    const cleaned = data.replace(/\s/g, "");
    if (!isValidBase64String(cleaned)) {
      alert("無効なBase64データです");
      setPastedBase64Data("");
      onAudioInfoChange(null);
      return;
    }
    if (!cleaned.startsWith("data:")) {
      dataUrl = "data:audio/mpeg;base64," + cleaned;
    }
    
    const audio = new Audio();
    audio.src = dataUrl;
    
    audio.onloadedmetadata = () => {
      onAudioInfoChange({
        duration: audio.duration,
        fileName: "Base64貼り付けデータ",
        fileSize: null,
        mimeType: audio.src.substring(5, audio.src.indexOf(";")),
      });
    };
    
    audio.onerror = () => {
      alert("無効な音声データです");
      setPastedBase64Data("");
      onAudioInfoChange(null);
    };
    
    setPastedBase64Data(dataUrl);
    setFileBase64Data("");
    onAudioDataChange(dataUrl);
  };

  const handleTextInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setFileBase64Data("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (value.trim() !== "") {
      processBase64Data(value);
    } else {
      onAudioInfoChange(null);
    }
  };

  const handleModeChange = (mode: "file" | "base64") => {
    if (mode === uploadMode) return;
    
    // モード切替時に状態をクリア
    setFileBase64Data("");
    setPastedBase64Data("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    onAudioDataChange("");
    onAudioInfoChange(null);
    
    setUploadMode(mode);
  };

  return (
    <div className="mb-6">
      <h2 className="text-xl font-bold mb-2">音声データのアップロード</h2>
      <div className="mb-4">
        <label className="mr-4 text-gray-200">
          <input
            type="radio"
            name="uploadMode"
            value="file"
            checked={uploadMode === "file"}
            onChange={() => handleModeChange("file")}
          />{" "}
          ファイル選択
        </label>
        <label className="text-gray-200">
          <input
            type="radio"
            name="uploadMode"
            value="base64"
            checked={uploadMode === "base64"}
            onChange={() => handleModeChange("base64")}
          />{" "}
          Base64貼り付け
        </label>
      </div>

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
          <label className="block mb-2">
            Base64エンコードされたデータを貼り付け
          </label>
          <textarea
            placeholder="Base64データを貼り付けてください"
            onChange={handleTextInputChange}
            value={pastedBase64Data}
            className="w-full p-2 text-black"
            rows={4}
          />
        </div>
      )}

      {audioData && (
        <div className="mb-4">
          <p className="text-sm">
            アップロードされたデータの先頭:{" "}
            <span className="text-green-300">{preview}</span>
          </p>
        </div>
      )}
    </div>
  );
};

export default AudioUploader;