import React, { useState, useRef, useEffect, ChangeEvent } from 'react';
import { Message, ChatRequest, ChatHistory } from '../../types/apiTypes';
import { useAuth } from '../../contexts/AuthContext';

// チャットコンテナのメインコンポーネント
const ChatContainer = () => {
  // ==========================
  //  ステートやRefの定義
  // ==========================
  const [currentChatId, setCurrentChatId] = useState<number | null>(null); // 現在のチャットID
  const { currentUser } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]); // チャットメッセージ
  const [input, setInput] = useState('');                  // テキスト入力
  const [isProcessing, setIsProcessing] = useState(false); // メッセージ処理中フラグ
  const [models, setModels] = useState<string[]>([]);      // 利用可能なAIモデル一覧
  const [selectedModel, setSelectedModel] = useState<string>(''); // 選択中のAIモデル
  const [chatHistories, setChatHistories] = useState<ChatHistory[]>([]); // チャット履歴
  const messageContainerRef = useRef<HTMLDivElement>(null);  // メッセージ表示エリアのref
  const abortControllerRef = useRef<AbortController | null>(null); // API通信中断用
  const [token, setToken] = useState<string>('');           // 認証トークン

  // 複数画像の一時保管用: base64文字列を配列で保持
  const [selectedImagesBase64, setSelectedImagesBase64] = useState<string[]>([]);

  // ==========================
  //  追加: エラーメッセージ用
  // ==========================
  const [errorMessage, setErrorMessage] = useState<string>('');

  // ==========================
  //  IndexedDB初期化
  // ==========================
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

  // ==========================
  //  認証トークンの取得
  // ==========================
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

  // ==========================
  //  メッセージ表示エリアの自動スクロール
  // ==========================
  useEffect(() => {
    if (messageContainerRef.current) {
      messageContainerRef.current.scrollTop = messageContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // ==========================
  //  利用可能なAIモデル一覧の取得
  // ==========================
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

  // ==========================
  //  IndexedDBから履歴を読み込み
  // ==========================
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
          .slice(0, 30);
        setChatHistories(sortedHistories);
      };
    };

    request.onerror = (event) => {
      console.error('履歴読み込みエラー:', (event.target as IDBRequest).error);
    };
  };

  // ==========================
  //  IndexedDBに履歴を保存
  // ==========================
  const saveChatHistory = async (currentMessages: Message[], chatId: number | null) => {
    if (currentMessages.length === 0) return;

    const newChatId = chatId ?? Date.now();
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

        const existingIndex = histories.findIndex((h) => h.id === chatId);
        let updatedHistories = [...histories];

        if (existingIndex !== -1) {
          // 既存履歴の更新
          updatedHistories[existingIndex] = {
            ...histories[existingIndex],
            messages: historyItem.messages,
            lastPromptDate: historyItem.lastPromptDate
          };
        } else {
          // 新規履歴の追加
          updatedHistories.push(historyItem);
        }

        // 最新30件のみを保持
        updatedHistories = updatedHistories
          .sort((a, b) => new Date(b.lastPromptDate).getTime() - new Date(a.lastPromptDate).getTime())
          .slice(0, 30);

        store.clear().onsuccess = () => {
          updatedHistories.forEach(history => store.add(history));
          setChatHistories(updatedHistories);
        };
      };
    };
  };

  // ==========================
  //  履歴を復元
  // ==========================
  const restoreHistory = (history: ChatHistory) => {
    setCurrentChatId(history.id);
    setMessages(history.messages);
  };

  // ==========================
  //  チャットをクリア
  // ==========================
  const clearChat = () => {
    setMessages([]);
    setCurrentChatId(null);
    setSelectedImagesBase64([]);
  };

  // ==========================
  //  画像アップロード(複数)
  // ==========================
  const handleImageUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const files = Array.from(e.target.files);

    const promises = files.map(file => {
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (event) => {
          if (event.target?.result) {
            resolve(event.target.result as string);
          } else {
            reject(new Error('Failed to read file'));
          }
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    });

    try {
      const newBase64s = await Promise.all(promises);
      setSelectedImagesBase64(prev => [...prev, ...newBase64s]);
    } catch (error) {
      console.error('画像アップロードエラー:', error);
    }
  };

  // ==========================
  //  選択画像を個別削除
  // ==========================
  const removeImage = (index: number) => {
    setSelectedImagesBase64((prev) => prev.filter((_, i) => i !== index));
  };

  // ==========================
  //  メッセージ送信
  // ==========================
  const sendMessage = async () => {
    // 送信前の状態をバックアップするための変数を事前に宣言
    let backupInput = '';
    let backupImages: string[] = [];
    let backupMessages: Message[] = [];
  
    // 入力テキストも画像も両方空なら送信しない
    if (!input.trim() && selectedImagesBase64.length === 0) return;
    // 既に処理中 or トークンなし は送信不可
    if (isProcessing || !token) return;
  
    // エラー表示をリセット
    setErrorMessage('');
  
    try {
      setIsProcessing(true);
  
      // ---- 送信前の状態をバックアップ ----
      backupInput = input;
      backupImages = [...selectedImagesBase64];
      backupMessages = [...messages];
  
      // ユーザーの新しいメッセージを作成
      const newUserMessage: Message = {
        role: 'user',
        content: input.trim() || '[Images Uploaded]',
        images: selectedImagesBase64.length > 0 ? [...selectedImagesBase64] : []
      };
  
      // 表示更新: ユーザーメッセージを追加
      let updatedMessages: Message[] = [...messages, newUserMessage];
      setMessages(updatedMessages);
  
      // 入力欄をクリア
      setInput('');
      setSelectedImagesBase64([]);
  
      // AbortControllerを用意
      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;
  
      // バックエンド送信用データ
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
        // アシスタントの空メッセージを先に追加
        updatedMessages = [...updatedMessages, { role: 'assistant', content: '' }];
        setMessages(updatedMessages);
  
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
  
          // 逐次メッセージをデコード
          const text = decoder.decode(value, { stream: true });
          assistantMessage += text;
  
          // リアルタイムで画面に反映
          setMessages((msgs) => {
            const newMsgs = [...msgs];
            newMsgs[newMsgs.length - 1] = {
              role: 'assistant',
              content: assistantMessage
            };
            return newMsgs;
          });
        }
      }
  
      // 最終的なアシスタントメッセージを更新
      updatedMessages[updatedMessages.length - 1].content = assistantMessage;
  
      // チャット履歴を保存
      await saveChatHistory(updatedMessages, currentChatId);
  
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        console.error('メッセージ送信エラー:', error);
  
        // ---- エラー時: バックアップから巻き戻す ----
        setMessages(backupMessages);
        setInput(backupInput);
        setSelectedImagesBase64(backupImages);
  
        // 3) ポップアップ(モーダル)でエラーを表示
        setErrorMessage(error instanceof Error ? error.message : '不明なエラー');
      }
    } finally {
      setIsProcessing(false);
      abortControllerRef.current = null;
    }
  };
  

  // ==========================
  //  キー押下時の送信トリガー
  // ==========================
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ==========================
  //  送信停止
  // ==========================
  const stopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsProcessing(false);
    }
  };

  // ==========================
  //  履歴ダウンロード
  // ==========================
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

  // ==========================
  //  履歴アップロード
  // ==========================
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
        console.error('履歴アップロードエラー:', error);
      }
    };
    reader.readAsText(file);
  };

  // ==========================
  //  JSXの描画部分
  // ==========================
  return (
    <div className="flex flex-1 h-[calc(100vh-64px)] mt-10 overflow-hidden">
      {/* -- エラーポップアップ（errorMessageが非空なら表示） -- */}
      {errorMessage && (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-10">
          <div className="bg-white p-6 rounded shadow">
            <h2 className="text-xl font-semibold mb-4">エラー</h2>
            <p className="mb-4">{errorMessage}</p>
            <button
              onClick={() => setErrorMessage('')}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              閉じる
            </button>
          </div>
        </div>
      )}

      {/* サイドバー */}
      <div className="w-64 bg-white shadow-lg p-4 overflow-y-auto">
        {/* モデル選択 */}
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

        {/* チャット履歴一覧 */}
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
                {/* テキスト表示 */}
                <div>{message.content}</div>

                {/* 複数画像を表示 */}
                {message.images && message.images.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {message.images.map((img, i) => (
                      <img
                        key={i}
                        src={img}
                        alt="Uploaded"
                        className="max-w-xs rounded border"
                      />
                    ))}
                  </div>
                )}
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
          {/* 選択画像プレビュー */}
          {selectedImagesBase64.length > 0 && (
            <div className="flex flex-wrap mb-4 gap-2">
              {selectedImagesBase64.map((imgBase64, i) => (
                <div key={i} className="relative inline-block">
                  <img
                    src={imgBase64}
                    alt="preview"
                    className="w-16 h-16 object-cover rounded border"
                  />
                  <button
                    className="absolute top-0 right-0 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center"
                    onClick={() => removeImage(i)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

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
            {/* 画像アップロードボタン（複数可能） */}
            <label className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded-lg cursor-pointer">
              画像選択
              <input
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={handleImageUpload}
                disabled={isProcessing}
              />
            </label>

            {/* 送信 or 停止 ボタン */}
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
