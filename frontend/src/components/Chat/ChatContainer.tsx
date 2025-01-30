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

// チャットコンテナのメインコンポーネント
const ChatContainer = () => {
  // ステート変数の定義
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);// 現在のチャットID
  const { currentUser } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]); // チャットメッセージの配列
  const [input, setInput] = useState(''); // ユーザー入力テキスト
  const [isProcessing, setIsProcessing] = useState(false); // メッセージ処理中フラグ
  const [models, setModels] = useState<string[]>([]); // 利用可能なAIモデルリスト
  const [selectedModel, setSelectedModel] = useState<string>(''); // 選択中のAIモデル
  const [chatHistories, setChatHistories] = useState<ChatHistory[]>([]); // チャット履歴
  const messageContainerRef = useRef<HTMLDivElement>(null); // メッセージ表示エリアのref
  const abortControllerRef = useRef<AbortController | null>(null); // API通信中断用コントローラー
  const [token, setToken] = useState<string>(''); // 認証トークン

  // IndexedDBの初期化とチャット履歴の読み込みを行うEffect
  useEffect(() => {
    const initDB = async () => {
      // データベースを開く（存在しない場合は作成）
      // 'ChatHistoryDB'という名前でバージョン1のデータベースを作成
      const request = indexedDB.open('ChatHistoryDB', 1);
      
      // データベース接続エラー時の処理
      request.onerror = (event) => {
        console.error('IndexedDB初期化エラー:', (event.target as IDBRequest).error);
      };
      
      // データベースのバージョンアップグレード時の処理
      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        // 'chatHistory'オブジェクトストアが存在しない場合のみ作成
        // keyPathとして'id'を指定し、一意のキーとして使用
        if (!db.objectStoreNames.contains('chatHistory')) {
          db.createObjectStore('chatHistory', { keyPath: 'id' });
        }
      };

      // データベース接続成功時の処理
      request.onsuccess = () => {
        console.log('IndexedDB初期化成功');
        // チャット履歴を読み込む
        loadChatHistories();
      };
    };
    
    // 初期化処理の実行
    initDB();
  }, []);

  // 認証トークンの取得処理
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

  // メッセージの自動スクロールと履歴保存
  useEffect(() => {
    if (messageContainerRef.current) {
      messageContainerRef.current.scrollTop = messageContainerRef.current.scrollHeight;
    }

  }, [messages]);

  // 利用可能なAIモデル一覧の取得
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
          setSelectedModel(data.models[0]);
        }
      } catch (error) {
        console.error('モデル一覧取得エラー:', error);
      }
    };

    fetchModels();
  }, [token]);

  const saveChatHistory = async (currentMessages: Message[],chatId: number | null) => {
    if (currentMessages.length === 0) return;
    
    const newChatId = chatId ?? Date.now();
    // 新規のチャットIDがまだ設定されていなければ、現在時刻をIDとして設定
    if (!currentChatId) {
      setCurrentChatId(newChatId);
    }
    
    
    const historyItem: ChatHistory = {
      id: newChatId,
      title: currentMessages[0].content.slice(0, 10) + '...',
      messages: [...currentMessages],
      date: new Date().toISOString(),
      lastPromptDate: new Date().toISOString()
    };

    const request = indexedDB.open('ChatHistoryDB', 1);
    request.onsuccess = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      const transaction = db.transaction(['chatHistory'], 'readwrite');
      const store = transaction.objectStore('chatHistory');

      store.getAll().onsuccess = (e) => {
        const histories = (e.target as IDBRequest).result as ChatHistory[];
        
        // 重複をチェックして新しい履歴のみを追加
        const existingIndex = histories.findIndex((h) => h.id === chatId);
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

  // IndexedDBからチャット履歴を読み込む関数
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

  // 選択したチャット履歴を復元する関数
  const restoreHistory = (history: ChatHistory) => {
    setCurrentChatId(history.id);
    setMessages(history.messages);
    // 履歴の更新や並び替えは行わない
  };

  // メッセージ送信処理
  const sendMessage = async () => {
    if (!input.trim() || isProcessing || !token) return;

    try {
      setIsProcessing(true);


      const newUserMessage: Message = { role: 'user', content: input.trim() };

      // 1. まず、ユーザーメッセージを既存messagesに加えた配列を自前で作る
      let updatedMessages: Message[] = [...messages, newUserMessage];

      // 2. それを一度 setMessages しつつ、以降の処理で参照できるように自己変数にも保持
      setMessages(updatedMessages);
      setInput('');

      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      const chatRequest: ChatRequest = {
        messages: updatedMessages,
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
        // 最初にアシスタントの空メッセージを追加
        updatedMessages = [...updatedMessages, { role: 'assistant', content: '' }];
        setMessages(updatedMessages);
        

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value, { stream: true });
          assistantMessage += text;
          

          // 即座に画面に反映されるよう、setMessagesを都度呼び出す
          setMessages(messages => {
            const newMessages = [...messages];
            newMessages[newMessages.length - 1] = {
              role: 'assistant',
              content: assistantMessage
            };
            return newMessages;
          });
        }
      }
      updatedMessages[updatedMessages.length - 1].content = assistantMessage;
      await saveChatHistory(updatedMessages, currentChatId);  
      }

      // 4. 全て受信し終わった段階で、上記updatedMessagesには
      //    「newUserMessage + 最終的なassistantメッセージ」がすでに含まれている
      //    よってsaveChatHistoryに渡せば、意図した内容で保存される
      

     catch (error: any) {
      if (error.name !== 'AbortError') {
        console.error('メッセージ送信エラー:', error);
        setMessages((prev) => [
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
  // キーボードイベントハンドラ（Enterキーでメッセージ送信）
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // メッセージ生成を停止する関数
  const stopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsProcessing(false);
    }
  };

  // チャットをクリアする関数
  const clearChat = () => {
    setMessages([]);
    setCurrentChatId(null);
  };

// サイドバーの既存のコードの中で、clearChatボタンの下に追加

// 履歴のダウンロード関数を追加
const downloadHistory = () => {
  const historyData = JSON.stringify(chatHistories, null, 2);
  const blob = new Blob([historyData], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `chat-history-${new Date().toISOString()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

// 履歴のアップロード関数を追加
const uploadHistory = async (event: React.ChangeEvent<HTMLInputElement>) => {
  const file = event.target.files?.[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const content = e.target?.result as string;
      const uploadedHistories = JSON.parse(content) as ChatHistory[];
      
      const request = indexedDB.open('ChatHistoryDB', 1);
      request.onsuccess = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        const transaction = db.transaction(['chatHistory'], 'readwrite');
        const store = transaction.objectStore('chatHistory');
        
        store.clear().onsuccess = () => {
          uploadedHistories.forEach(history => store.add(history));
          setChatHistories(uploadedHistories);
        };
      };
    } catch (error) {
      console.error('履歴のアップロードエラー:', error);
    }
  };
  reader.readAsText(file);
};



  // UIレンダリング
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

          <div className="flex space-x-2 mb-6">
            <button
              onClick={downloadHistory}
              className="flex-1 p-2 bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
            >
              履歴保存
            </button>
            <label className="flex-1">
              <input
                type="file"
                accept=".json"
                onChange={uploadHistory}
                className="hidden"
              />
              <span className="block p-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg transition-colors text-center cursor-pointer">
                履歴読込
              </span>
            </label>
          </div>
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