// frontend/src/components/Chat/ChatMessages.tsx
import React, { useRef, useEffect } from "react";
import { Message } from "../../types/apiTypes";
import { FileData } from "../../utils/fileUtils";

interface ChatMessagesProps {
  messages: Message[];
  onEditPrompt: (index: number) => void;
}

const ChatMessages: React.FC<ChatMessagesProps> = ({ 
  messages, 
  onEditPrompt 
}) => {
  const messageContainerRef = useRef<HTMLDivElement>(null);

  // メッセージ表示エリアの自動スクロール
  useEffect(() => {
    if (messageContainerRef.current) {
      messageContainerRef.current.scrollTop =
        messageContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // ファイルタイプに応じたアイコン表示
  const getFileIcon = (mimeType: string) => {
    if (mimeType.startsWith('image/')) return "🖼️";
    if (mimeType.startsWith('audio/')) return "🔊";
    if (mimeType === 'text/csv') return "📊";
    if (mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return "📝";
    if (mimeType === 'application/pdf') return "📄";
    return "📎";
  };

  return (
    <div
      ref={messageContainerRef}
      className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-900"
    >
      {messages.map((message, index) => (
        <div
          key={index}
          className={`max-w-[80%] ${
            message.role === "user" ? "ml-auto" : "mr-auto"
          }`}
        >
          <div
            className={`p-4 rounded-lg ${
              message.role === "user"
                ? "bg-blue-900 text-gray-100"
                : "bg-gray-800 border border-gray-700 text-gray-100"
            }`}
          >
            {message.role === "user" ? (
              <div className="flex justify-between items-center">
                <div>{message.content}</div>
                <button
                  onClick={() => onEditPrompt(index)}
                  className="ml-2 text-sm text-gray-300 hover:text-gray-100"
                  title="このプロンプトを編集して再送信"
                >
                  編集
                </button>
              </div>
            ) : (
              <div>{message.content}</div>
            )}

            {/* ファイル表示 */}
            {message.files && message.files.length > 0 && (
              <div className="mt-2">
                <div className="text-sm text-gray-300 mb-1">
                  添付ファイル:
                </div>
                <div className="flex flex-wrap gap-2">
                  {message.files.map((file: FileData) => (
                    <div
                      key={file.id}
                      className="relative cursor-pointer"
                    >
                      {file.mimeType.startsWith('image/') ? (
                        <img
                          src={file.content}
                          alt={file.name}
                          className="w-16 h-16 object-cover rounded border"
                        />
                      ) : (
                        <div className="p-2 bg-gray-700 rounded border border-gray-600 flex items-center">
                          <span className="mr-2">
                            {getFileIcon(file.mimeType)}
                          </span>
                          <span className="text-sm truncate max-w-[150px]">
                            {file.name}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div
            className={`text-xs text-gray-400 mt-1 ${
              message.role === "user" ? "text-right" : "text-left"
            }`}
          >
            {message.role === "user" ? "あなた" : "アシスタント"}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ChatMessages;