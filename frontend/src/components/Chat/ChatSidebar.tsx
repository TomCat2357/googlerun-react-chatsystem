// frontend/src/components/Chat/ChatSidebar.tsx
import React, { ChangeEvent } from "react";
import { ChatHistory } from "../../types/apiTypes";

interface ChatSidebarProps {
  models: string[];
  selectedModel: string;
  onModelChange: (model: string) => void;
  chatHistories: ChatHistory[];
  currentChatId: number | null;
  onNewChat: () => void;
  onSelectHistory: (chatId: number) => void;
  onClearAll: () => void;
  onDownloadHistory: () => void;
  onUploadHistory: (event: ChangeEvent<HTMLInputElement>) => void;
  onDeleteHistory: (chatId: number) => void;
}

const ChatSidebar: React.FC<ChatSidebarProps> = ({
  models,
  selectedModel,
  onModelChange,
  chatHistories,
  currentChatId,
  onNewChat,
  onSelectHistory,
  onClearAll,
  onDownloadHistory,
  onUploadHistory,
  onDeleteHistory,
}) => {
  // 削除ボタンのクリック時にイベントの伝播を止める
  const handleDeleteClick = (
    e: React.MouseEvent<HTMLButtonElement>,
    historyId: number
  ) => {
    e.stopPropagation(); // 重要：これがないとチャット履歴の選択も同時に実行されてしまう
    if (onDeleteHistory) {
      if (window.confirm("この履歴を削除してもよろしいですか？")) {
        onDeleteHistory(historyId);
      }
    }
  };

  return (
    <div className="w-64 bg-gray-800 shadow-lg p-4 overflow-y-auto">
      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-4 text-gray-100">
          モデル選択
        </h2>
        <select
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
          className="w-full p-2 bg-gray-700 border-gray-600 text-gray-100 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <button
        onClick={onNewChat}
        className="w-full mb-6 p-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg transition-colors"
      >
        新規チャット
      </button>
      <div className="flex space-x-2 mb-6">
        <button
          onClick={onDownloadHistory}
          className="flex-1 p-2 bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
        >
          履歴保存
        </button>
        <label className="flex-1">
          <input
            type="file"
            accept=".json"
            onChange={onUploadHistory}
            className="hidden"
          />
          <span className="block p-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg transition-colors text-center cursor-pointer">
            履歴読込
          </span>
        </label>
      </div>
      <div>
        <h2 className="text-lg font-semibold mb-4 text-gray-100">
          最近のチャット
        </h2>
        <div className="space-y-2">
          {chatHistories.map((history) => (
            <div
              key={history.id}
              onClick={() => onSelectHistory(history.id!)}
              className="p-2 hover:bg-gray-700 text-gray-100 rounded cursor-pointer transition-colors relative"
            >
              <div className="font-medium pr-6">{history.title}</div>
              <div className="text-sm text-gray-400">
                {new Date(history.updatedAt).toLocaleString()}
              </div>
              {/* 削除ボタン（バツ印） */}
              <button
                onClick={(e) => handleDeleteClick(e, history.id!)}
                className="absolute top-2 right-2 w-5 h-5 flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-gray-600 rounded-full"
                title="この履歴を削除"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ChatSidebar;