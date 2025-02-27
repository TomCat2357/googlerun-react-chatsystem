// frontend/src/components/SpeechToText/MetadataEditor.tsx
import React from "react";

interface MetadataEditorProps {
  description: string;
  recordingDate: string;
  isSending: boolean;
  onDescriptionChange: (description: string) => void;
  onRecordingDateChange: (date: string) => void;
  onSend: () => void;
}

const MetadataEditor: React.FC<MetadataEditorProps> = ({
  description,
  recordingDate,
  isSending,
  onDescriptionChange,
  onRecordingDateChange,
  onSend
}) => {
  return (
    <div className="border border-gray-400 rounded p-4 mb-6 flex flex-col justify-end" style={{ minHeight: "150px" }}>
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200">
          説明
        </label>
        <input
          type="text"
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          maxLength={20}
          placeholder="20文字以内"
          className="w-full p-2 text-black"
        />
      </div>
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200">
          録音日
        </label>
        <input
          type="text"
          value={recordingDate}
          onChange={(e) => onRecordingDateChange(e.target.value)}
          placeholder="YYYY/MM/dd"
          className="w-full p-2 text-black"
        />
      </div>
      <button
        onClick={onSend}
        disabled={isSending}
        className="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
      >
        {isSending ? "処理中..." : "送信"}
      </button>
    </div>
  );
};

export default MetadataEditor;