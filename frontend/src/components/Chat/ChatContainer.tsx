import React, { useState, useRef, useEffect } from 'react';
import { Message, ChatRequest } from '../../types/apiTypes';
import { useAuth } from '../../contexts/AuthContext';

// インターフェースの更新
interface ChatHistory {
  id: number;
  title: string;
  messages: Message[];
  date: string;
  lastPromptDate: string; // 新しく追加
}

const ChatContainer = () => {
  const { currentUser } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [chatHistories, setChatHistories] = useState<ChatHistory[]>([]);
  const messageContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [token, setToken] = useState<string>('');

  // IndexedDB初期化
  useEffect(() => {
    const initDB = async () => {
      const request = indexedDB.open('ChatHistoryDB', 1);
      
      request.onerror = (event) => {
        console.error('IndexedDB初期化エラー:', (event.target as IDBRequest).error);
      };
      
      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains('chatHistory')) {
          db.createObjectStore('chatHistory', { keyPath: 'id' });
        }
      };

      request.onsuccess = () => {
        console.log('IndexedDB初期化成功');
        loadChatHistories();
      };
    };
    
    initDB();
  }, []);

  // トークン取得
  useEffect(() => {
    const fetchToken = async () => {
      if (currentUser) {
        try {
          const t = await currentUser.getIdToken();
          setToken(t);
          console.log('トークン取得成功');
        } catch (error) {
          console.error('トークン取得エラー:', error);
        }
      }
    };
    fetchToken();
  }, [currentUser]);

  // メッセージ自動スクロールと履歴保存
  useEffect(() => {
    if (messageContainerRef.current) {
      messageContainerRef.current.scrollTop = messageContainerRef.current.scrollHeight;
    }

    if (messages.length > 0) {
      saveChatHistory();
    }
  }, [messages]);

  // モデル一覧取得
  useEffect(() => {
    const fetchModels = async () => {
      if (!token) return;

      try {
        const response = await fetch('http://localhost:8080/app/models', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        });
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        if (Array.isArray(data.models)) {
          setModels(data.models);
          setSelectedModel(data.models[0] || '');
        }
      } catch (error) {
        console.error('モデル一覧取得エラー:', error);
      }
    };

    fetchModels();
  }, [token]);

  const saveChatHistory = async () => {
    if (messages.length === 0) return;

    const historyItem: ChatHistory = {
      id: Date.now(),
      title: messages[0].content.slice(0, 10) + '...',
      messages: [...messages],
      date: new Date().toISOString(),
      lastPromptDate: new Date().toISOString() // 新しく追加
    };

    const request = indexedDB.open('ChatHistoryDB', 1);
    request.onsuccess = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      const transaction = db.transaction(['chatHistory'], 'readwrite');
      const store = transaction.objectStore('chatHistory');

      store.getAll().onsuccess = (e) => {
        const histories = (e.target as IDBRequest).result as ChatHistory[];
        
        // 重複をチェックして新しい履歴のみを追加
        const existingIndex = histories.findIndex(h => 
          h.messages[0]?.content === historyItem.messages[0]?.content
        );
        let updatedHistories = [...histories];
        
        if (existingIndex !== -1) {
          // 既存の履歴を更新（メッセージと最終プロンプト時間のみ更新）
          updatedHistories[existingIndex] = {
            ...histories[existingIndex],
            messages: historyItem.messages,
            lastPromptDate: historyItem.lastPromptDate
          };
        } else {
          // 新しい履歴を追加
          updatedHistories.push(historyItem);
        }
        
        // 最終プロンプト時間でソートして最新5件のみを保持
        updatedHistories = updatedHistories
          .sort((a, b) => new Date(b.lastPromptDate).getTime() - new Date(a.lastPromptDate).getTime())
          .slice(0, 5);
        
        store.clear().onsuccess = () => {
          updatedHistories.forEach(history => store.add(history));
          setChatHistories(updatedHistories);
        };
      };
    };
  };

  const loadChatHistories = async () => {
    const request = indexedDB.open('ChatHistoryDB', 1);
    request.onsuccess = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      const transaction = db.transaction(['chatHistory'], 'readonly');
      const store = transaction.objectStore('chatHistory');

      store.getAll().onsuccess = (e) => {
        const histories = (e.target as IDBRequest).result as ChatHistory[];
        const sortedHistories = histories
          .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
          .slice(0, 5);
        setChatHistories(sortedHistories);
      };
    };

    request.onerror = (event) => {
      console.error('履歴読み込みエラー:', (event.target as IDBRequest).error);
    };
  };

  // restoreHistory関数の修正 - メッセージの復元のみを行い、順序は変更しない
  const restoreHistory = (history: ChatHistory) => {
    setMessages(history.messages);
    // 履歴の更新や並び替えは行わない
  };

  const sendMessage = async () => {
    if (!input.trim() || isProcessing || !token) return;

    try {
      setIsProcessing(true);
      const newUserMessage: Message = { role: 'user', content: input.trim() };
      setMessages(prev => [...prev, newUserMessage]);
      setInput('');

      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      const chatRequest: ChatRequest = {
        messages: [...messages, newUserMessage],
        model: selectedModel
      };

      const response = await fetch('http://localhost:8080/app/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Authorization': `Bearer ${token}`
        },
        signal,
        body: JSON.stringify(chatRequest)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      let assistantMessage = '';
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const text = decoder.decode(value, { stream: true });
          assistantMessage += text;
          setMessages(prev => {
            const newMessages = [...prev];
            const lastMessage = newMessages[newMessages.length - 1];
            if (lastMessage && lastMessage.role === 'assistant') {
              lastMessage.content = assistantMessage;
              return [...newMessages];
            } else {
              return [...newMessages, { role: 'assistant', content: assistantMessage }];
            }
          });
        }
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        console.error('メッセージ送信エラー:', error);
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: 'エラーが発生しました: ' + (error instanceof Error ? error.message : '不明なエラー')
          }
        ]);
      }
    } finally {
      setIsProcessing(false);
      abortControllerRef.current = null;
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const stopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsProcessing(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* サイドバー */}
      <div className="w-64 bg-white shadow-lg p-4">
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-4">モデル選択</h2>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="w-full p-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <button
          onClick={clearChat}
          className="w-full mb-6 p-2 bg-gray-200 hover:bg-gray-300 rounded-lg transition-colors"
        >
          新規チャット
        </button>

        {/* チャット履歴 */}
        <div>
          <h2 className="text-lg font-semibold mb-4">最近のチャット</h2>
          <div className="space-y-2">
            {chatHistories.map((history) => (
              <div
                key={history.id}
                onClick={() => restoreHistory(history)}
                className="p-2 hover:bg-gray-100 rounded cursor-pointer transition-colors"
              >
                <div className="font-medium">{history.title}</div>
                <div className="text-sm text-gray-500">
                  {new Date(history.lastPromptDate).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* メインチャットエリア */}
      <div className="flex-1 flex flex-col h-full">
        {/* メッセージ表示エリア */}
        <div
          ref={messageContainerRef}
          className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50"
        >
          {messages.map((message, index) => (
            <div
              key={index}
              className={`max-w-[80%] ${
                message.role === 'user' ? 'ml-auto' : 'mr-auto'
              }`}
            >
              <div
                className={`p-4 rounded-lg ${
                  message.role === 'user'
                    ? 'bg-blue-100 text-gray-900'
                    : 'bg-white border-2 border-gray-200 shadow-sm text-gray-800'
                }`}
              >
                {message.content}
              </div>
              <div
                className={`text-xs text-gray-500 mt-1 ${
                  message.role === 'user' ? 'text-right' : 'text-left'
                }`}
              >
                {message.role === 'user' ? 'あなた' : 'アシスタント'}
              </div>
            </div>
          ))}
        </div>

        {/* 入力エリア */}
        <div className="border-t p-4 bg-white">
          <div className="flex space-x-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              className="flex-1 p-2 border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="メッセージを入力..."
              rows={2}
              disabled={isProcessing}
            />
            <button
              onClick={isProcessing ? stopGeneration : sendMessage}
              className={`px-4 py-2 rounded-lg ${
                isProcessing
                  ? 'bg-red-500 hover:bg-red-600'
                  : 'bg-blue-500 hover:bg-blue-600'
              } text-white transition-colors`}
            >
              {isProcessing ? '停止' : '送信'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatContainer;