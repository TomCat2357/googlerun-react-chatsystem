// frontend/src/components/Chat/ChatInput.tsx
import React, { ChangeEvent } from "react";
import { FileData } from "../../utils/fileUtils";

interface ChatInputProps {
  input: string;
  setInput: (input: string) => void;
  isProcessing: boolean;
  selectedFiles: FileData[];
  addFiles: (event: React.ChangeEvent<HTMLInputElement>) => void;
  sendMessage: () => void;
  stopGeneration: () => void;
  setErrorMessage: (message: string) => void;
  maxLimits: {
    MAX_IMAGES: number;
    MAX_AUDIO_FILES: number;
    MAX_TEXT_FILES: number;
    MAX_IMAGE_SIZE: number;
    MAX_LONG_EDGE: number;
  };
}

const ChatInput: React.FC<ChatInputProps> = ({
  input,
  setInput,
  isProcessing,
  selectedFiles,
  addFiles,
  sendMessage,
  stopGeneration,
  setErrorMessage,
  maxLimits
}) => {

  const handleSendMessage = () => {
    if ((!input.trim() && selectedFiles.length === 0) || isProcessing) return;
    sendMessage();
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex flex-col space-y-2">
      {/* ファイル選択ボタン */}
      <div className="flex space-x-2">
        <input
          type="file"
          id="imageUpload"
          accept="image/*"
          multiple
          onChange={addFiles}
          style={{ display: "none" }}
        />
        <label
          htmlFor="imageUpload"
          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded cursor-pointer transition-colors text-sm"
        >
          📷 画像
        </label>

        <input
          type="file"
          id="audioUpload"
          accept="audio/*"
          onChange={addFiles}
          style={{ display: "none" }}
        />
        <label
          htmlFor="audioUpload"
          className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded cursor-pointer transition-colors text-sm"
        >
          🎵 音声
        </label>

        <input
          type="file"
          id="textUpload"
          accept=".txt,.csv,.pdf,.docx"
          multiple
          onChange={addFiles}
          style={{ display: "none" }}
        />
        <label
          htmlFor="textUpload"
          className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded cursor-pointer transition-colors text-sm"
        >
          📄 テキスト
        </label>
      </div>

      {/* メッセージ入力エリア */}
      <div className="flex items-end space-x-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="メッセージを入力..."
          className="flex-1 p-3 bg-gray-700 text-white rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          rows={3}
          disabled={isProcessing}
        />
        
        <div className="flex flex-col space-y-2">
          {isProcessing ? (
            <button
              onClick={stopGeneration}
              className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
              type="button"
            >
              停止
            </button>
          ) : (
            <button
              onClick={handleSendMessage}
              disabled={!input.trim() && selectedFiles.length === 0}
              className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
              type="button"
            >
              送信
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatInput;