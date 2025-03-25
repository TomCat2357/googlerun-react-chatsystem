// frontend/src/component/Whisper/WhisperMetadataEditor.tsx
import React from "react";

interface WhisperMetadataEditorProps {
  description: string;
  recordingDate: string;
  isSending: boolean;
  onDescriptionChange: (description: string) => void;
  onRecordingDateChange: (date: string) => void;
  onSend: () => void;
}

const WhisperMetadataEditor: React.FC<WhisperMetadataEditorProps> = ({
  description,
  recordingDate,
  isSending,
  onDescriptionChange,
  onRecordingDateChange,
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