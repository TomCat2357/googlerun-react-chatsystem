// frontend/src/component/Whisper/WhisperUploader.tsx
import React, { useRef, useState, useEffect } from "react";
import { toast } from "react-toastify";
import * as Config from "../../config";
import axios from "axios";

export interface AudioInfo {
  duration: number;
  fileName?: string;
  fileSize?: number | null;
  mimeType?: string;
}

interface WhisperUploaderProps {
  onAudioDataChange: (audioData: string) => void;
  onAudioInfoChange: (audioInfo: AudioInfo | null) => void;
  onDescriptionChange: (description: string) => void;
  onRecordingDateChange: (date: string) => void;
  onTagsChange?: (tags: string[]) => void;
  onLanguageChange?: (language: string) => void;
  onInitialPromptChange?: (prompt: string) => void;
}

const WhisperUploader: React.FC<WhisperUploaderProps> = ({
  onAudioDataChange,
  onAudioInfoChange,
  onDescriptionChange,
  onRecordingDateChange,
  onTagsChange
}) => {
  // 基本的な状態管理
  const [fileBase64Data, setFileBase64Data] = useState("");
  const [pastedBase64Data, setPastedBase64Data] = useState("");
  const [dragActive, setDragActive] = useState(false);
  
  // タグ関連の状態
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  
  // 参照
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // 表示用の音声データ
  const audioData = fileBase64Data || pastedBase64Data;
  const preview = audioData.substring(0, 30);

  // 日付フォーマット関数
  const formatDate = (timestamp: number): string => {
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = ("0" + (date.getMonth() + 1)).slice(-2);
    const day = ("0" + date.getDate()).slice(-2);
    return `${year}/${month}/${day}`;
  };

  // サーバー設定から最大ファイルサイズを取得 (デフォルトは10MB)
  const MAX_BYTES = Config.getServerConfig().WHISPER_MAX_BYTES || 10 * 1024 * 1024;

  // ファイル処理関数（署名付きURLを使用）
  const processFile = async (file: File) => {
    if (!file.type.startsWith("audio/")) {
      alert("音声ファイル以外はアップロードできません");
      return;
    }
    
    // ファイルサイズチェック
    if (file.size > MAX_BYTES) {
      toast.error(`${(MAX_BYTES/1024/1024).toFixed(1)} MB を超えるファイルはアップロードできません`);
      return;
    }
    
    // ファイルの長さをチェック
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.src = url;
    
    try {
      // 先に音声のメタデータを読み込む
      await new Promise<void>((resolve, reject) => {
        // ブラウザ差異を考慮した安全版の音声長さ取得
        const getDurationSafely = (file: File): Promise<number> => {
          return new Promise<number>(resolve => {
            const audio = new Audio();
            audio.preload = "metadata";
            audio.onloadedmetadata = () => resolve(audio.duration);
            audio.onerror = () => resolve(Number.MAX_VALUE);  // 失敗時はbackend側で検証
            audio.src = URL.createObjectURL(file);
          });
        };
        
        // 音声長さを取得
        const duration = await getDurationSafely(file);
        
        onAudioInfoChange({
          duration: duration,
          fileName: file.name,
          fileSize: file.size,
          mimeType: file.type,
        });
        resolve();
      });
      
      // 音声長さチェック
      if (audio.duration > Config.getServerConfig().WHISPER_MAX_SECONDS) {
        URL.revokeObjectURL(url);
        toast.error(`音声の長さが制限を超えています(最大${Math.floor(Config.getServerConfig().WHISPER_MAX_SECONDS/60)}分)`);
        return;
      }
      
      // 署名付きURLを取得
      const API_BASE_URL = Config.API_BASE_URL;
      const token = localStorage.getItem("token");
      
      if (!token) {
        toast.error("認証トークンがありません");
        return;
      }
      
      // 署名付きURLの取得
      const uploadUrlResponse = await axios.post(
        `${API_BASE_URL}/backend/whisper/upload_url`,
        { content_type: file.type },
        {
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          }
        }
      );
      
      // 署名付きURLを使って直接GCSにアップロード
      await fetch(uploadUrlResponse.data.upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file
      });
      
      // Uploaderコンポーネント用の状態更新
      setPastedBase64Data("");
      onAudioDataChange("gs://" + uploadUrlResponse.data.object_name);
      onDescriptionChange(file.name);
      onRecordingDateChange(formatDate(file.lastModified));
      
      toast.success("ファイルのアップロードが完了しました");
      
    } catch (error) {
      console.error("ファイル処理エラー:", error);
      toast.error(error instanceof Error ? error.message : "ファイル処理中にエラーが発生しました");
      setFileBase64Data("");
      setPastedBase64Data("");
      onAudioInfoChange(null);
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  // ファイル選択イベントハンドラ
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
  };

  // ドラッグ&ドロップ関連のイベントハンドラ
  const handleDrag = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };
  
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    processFile(file);
  };

  // Base64データの検証
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

  // Base64データ処理関数
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

  // テキスト入力イベントハンドラ
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


  // タグ追加ハンドラ
  const addTag = () => {
    if (newTag && !tags.includes(newTag)) {
      const updatedTags = [...tags, newTag];
      setTags(updatedTags);
      if (onTagsChange) onTagsChange(updatedTags);
      setNewTag("");
    }
  };
  
  // タグ削除ハンドラ
  const removeTag = (tagToRemove: string) => {
    const updatedTags = tags.filter(tag => tag !== tagToRemove);
    setTags(updatedTags);
    if (onTagsChange) onTagsChange(updatedTags);
  };

  return (
    <div className="mb-6">
      <div className="bg-gray-800 p-4 rounded-t border-b border-gray-600">
        <h2 className="text-xl font-bold mb-2">音声データのアップロード</h2>
        <p className="text-gray-300 mb-4">
          ※アップロードした音声はバッチ処理で文字起こしされます。処理完了後、メールで通知されます。
        </p>
        
      </div>

      <div className="bg-gray-700 p-4 rounded-b">
        {/* ファイルアップロードUI */}
        <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-8 mb-4 text-center cursor-pointer transition-colors ${
              dragActive ? "border-blue-500 bg-blue-500/10" : "border-gray-400"
            }`}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="flex flex-col items-center justify-center">
              <span className="text-4xl mb-2">🎤</span>
              <p className="mb-2">
                ここにドラッグ＆ドロップするか、クリックしてファイルを選択してください
              </p>
              <p className="text-sm text-gray-400">
                サポートしている形式: MP3, WAV, M4A, OGG, FLAC など
              </p>
            </div>
            <input
              type="file"
              ref={fileInputRef}
              accept="audio/*"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>

        {/* アップロードデータのプレビュー */}
        {audioData && (
          <div className="mb-4 p-3 bg-gray-800 rounded">
            <p className="text-sm text-gray-300">
              アップロードされたデータの先頭:{" "}
              <span className="text-green-300 font-mono">{preview}...</span>
            </p>
          </div>
        )}

        {/* タグ付け機能 */}
        <div className="mt-6 border border-gray-600 rounded p-4">
          <label className="block text-sm font-medium mb-2">タグ付け（オプション）</label>
          <div className="flex flex-wrap gap-2 mb-2 min-h-8">
            {tags.map(tag => (
              <span key={tag} className="bg-blue-800 px-2 py-1 rounded text-sm flex items-center">
                {tag}
                <button 
                  className="ml-2 text-xs"
                  onClick={() => removeTag(tag)}
                >
                  ×
                </button>
              </span>
            ))}
            {tags.length === 0 && (
              <span className="text-gray-400 text-sm">タグはまだありません</span>
            )}
          </div>
          <div className="flex">
            <input
              type="text"
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && addTag()}
              placeholder="タグを追加（例: 会議, 議事録）"
              className="flex-grow p-2 text-black rounded-l"
            />
            <button
              onClick={addTag}
              className="bg-blue-500 hover:bg-blue-600 px-3 py-2 rounded-r"
            >
              追加
            </button>
          </div>
          <p className="mt-2 text-gray-400 text-xs">
            タグを使って音声ファイルを分類できます。Enterキーまたは「追加」ボタンでタグを追加します。
          </p>
        </div>
      </div>
    </div>
  );
};

export default WhisperUploader;