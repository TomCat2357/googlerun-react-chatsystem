import React, { useState } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const ChatContainer = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedModel, setSelectedModel] = useState('anthropic/claude-3-haiku-20240307');
  const [isProcessing, setIsProcessing] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isProcessing) return;

    console.log('Message to send:', inputMessage);
    console.log('Selected model:', selectedModel);
  };

  return (
    <div className="flex h-screen bg-white">
      {/* サイドバー */}
      <div className="w-64 bg-gray-50 border-r border-gray-200 p-4">
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="w-full p-2 mb-4 border rounded bg-white text-gray-900"
        >
          <option value="anthropic/claude-3-haiku-20240307">Claude 3 Haiku</option>
          <option value="ollama/aya:latest">Aya</option>
          <option value="ollama/phi3:mini">Phi-3 Mini</option>
        </select>
        <button 
          className="w-full p-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 border border-gray-300"
          onClick={() => setMessages([])}
        >
          新規チャットを始める
        </button>
      </div>

      {/* メインチャットエリア */}
      <div className="flex-1 flex flex-col bg-white">
        {/* メッセージ表示エリア */}
        <div className="flex-1 overflow-y-auto p-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`mb-4 p-3 rounded max-w-3xl ${
                message.role === 'user' 
                  ? 'bg-blue-50 ml-auto text-gray-900' 
                  : 'bg-gray-50 text-gray-900'
              }`}
            >
              {message.content}
            </div>
          ))}
        </div>

        {/* 入力エリア */}
        <div className="border-t border-gray-200 p-4 bg-white">
          <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
            <div className="flex gap-2">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                className="flex-1 p-2 border border-gray-300 rounded bg-white text-gray-900"
                placeholder="メッセージを入力..."
                disabled={isProcessing}
              />
              <button
                type="submit"
                disabled={isProcessing}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {isProcessing ? '送信中...' : '送信'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default ChatContainer;