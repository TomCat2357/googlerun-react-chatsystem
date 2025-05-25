// frontend/src/component/Whisper/WhisperMetadataEditor.tsx
import React from "react";

interface WhisperMetadataEditorProps {
  description: string;
  recordingDate: string;
  language?: string;
  initialPrompt?: string;
  isSending: boolean;
  onDescriptionChange: (description: string) => void;
  onRecordingDateChange: (date: string) => void;
  onLanguageChange?: (language: string) => void;
  onInitialPromptChange?: (prompt: string) => void;
  onSend: () => void;
}

const WhisperMetadataEditor: React.FC<WhisperMetadataEditorProps> = ({
  description,
  recordingDate,
  language = "ja",
  initialPrompt = "",
  isSending,
  onDescriptionChange,
  onRecordingDateChange,
  onLanguageChange,
  onInitialPromptChange,
  onSend
}) => {
  return (
    <div className="border border-gray-400 rounded p-4 mb-6 flex flex-col">
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200">説明</label>
        <input
          type="text"
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          maxLength={20}
          placeholder="説明 (20文字以内)"
          className="w-full p-2 text-black"
        />
      </div>
      
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200">録音日</label>
        <input
          type="text"
          value={recordingDate}
          onChange={(e) => onRecordingDateChange(e.target.value)}
          placeholder="YYYY/MM/DD"
          className="w-full p-2 text-black"
        />
      </div>

      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200">言語</label>
        <select
          value={language}
          onChange={(e) => onLanguageChange && onLanguageChange(e.target.value)}
          className="w-full p-2 text-black"
        >
          <option value="ja">日本語</option>
          <option value="en">英語</option>
          <option value="zh">中国語</option>
          <option value="ko">韓国語</option>
          <option value="fr">フランス語</option>
          <option value="de">ドイツ語</option>
          <option value="es">スペイン語</option>
          <option value="it">イタリア語</option>
          <option value="pt">ポルトガル語</option>
          <option value="ru">ロシア語</option>
        </select>
        <p className="text-xs text-gray-400 mt-1">※音声の主要言語を選択してください</p>
      </div>
      
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200">初期プロンプト（オプション）</label>
        <textarea
          value={initialPrompt}
          onChange={(e) => onInitialPromptChange && onInitialPromptChange(e.target.value)}
          placeholder="専門用語や固有名詞などを入力すると精度が向上します"
          className="w-full p-2 text-black"
          rows={3}
        />
        <p className="text-xs text-gray-400 mt-1">※頻出する専門用語や固有名詞を入力することで認識精度が向上します</p>
      </div>
      
      <button
        onClick={onSend}
        disabled={isSending}
        className={`
          px-4 py-2 rounded font-bold self-start
          ${isSending ? 'bg-gray-500 cursor-not-allowed' : 'bg-blue-500 hover:bg-blue-600'}
        `}
      >
        {isSending ? "アップロード中..." : "アップロード＆処理開始"}
      </button>
      
      <p className="mt-2 text-gray-300 text-sm">
        ※処理完了後、登録されたメールアドレスに通知が届きます
      </p>
    </div>
  );
};

export default WhisperMetadataEditor;