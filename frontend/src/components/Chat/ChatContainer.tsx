import React, { useState, useRef, useEffect, ChangeEvent } from 'react';
import { Message, ChatRequest, ChatHistory} from '../../types/apiTypes';
import { useAuth } from '../../contexts/AuthContext';



// チャットコンテナのメインコンポーネント
const ChatContainer = () => {
  // ステート変数の定義
  const [currentChatId, setCurrentChatId] = useState<number | null>(null); // 現在のチャットID
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

  // 複数画像の一時保管用: base64文字列を配列で保持
  const [selectedImagesBase64, setSelectedImagesBase64] = useState<string[]>([]);

  // IndexedDBの初期化とチャット履歴の読み込みを行うEffect
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
        // チャット履歴を読み込む
        loadChatHistories();
      };
    };

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

  // メッセージの自動スクロール
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
          .slice(0, 30);
        setChatHistories(sortedHistories);
      };
    };

    request.onerror = (event) => {
      console.error('履歴読み込みエラー:', (event.target as IDBRequest).error);
    };
  };

  // チャット履歴を保存する
  const saveChatHistory = async (currentMessages: Message[], chatId: number | null) => {
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

        // 最終プロンプト時間でソートして最新30件のみを保持
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

  // 選択したチャット履歴を復元する
  const restoreHistory = (history: ChatHistory) => {
    setCurrentChatId(history.id);
    setMessages(history.messages);
  };

  // 画像を選択したときに呼ばれるハンドラ (複数対応)
  const handleImageUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const files = Array.from(e.target.files);

    // FileReader で非同期にbase64変換し、すべてPromiseで受け取る
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

  // 選択画像の個別削除
  const removeImage = (index: number) => {
    setSelectedImagesBase64((prev) => prev.filter((_, i) => i !== index));
  };

  // メッセージ送信処理
  const sendMessage = async () => {
    // テキスト入力も画像も両方何もない場合は送信しない
    if (!input.trim() && selectedImagesBase64.length === 0) return;
    if (isProcessing || !token) return;

    try {
      setIsProcessing(true);

      // ユーザーの新しいメッセージ
      const newUserMessage: Message = {
        role: 'user',
        // テキストが空で画像のみの場合はダミー文言を入れておく
        content: input.trim() || '[Images Uploaded]',
        images: selectedImagesBase64.length > 0 ? [...selectedImagesBase64] : []
      };

      let updatedMessages: Message[] = [...messages, newUserMessage];

      // 画面に即時反映
      setMessages(updatedMessages);
      setInput('');
      setSelectedImagesBase64([]); // 送信後はリセット

      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      // バックエンドへの送信用にまとめる
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
        // アシスタントの空メッセージを追加
        updatedMessages = [...updatedMessages, { role: 'assistant', content: '' }];
        setMessages(updatedMessages);

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value, { stream: true });
          assistantMessage += text;

          // 逐次画面更新
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

      // 最終的なアシスタントメッセージを反映
      updatedMessages[updatedMessages.length - 1].content = assistantMessage;
      // 履歴を保存
      await saveChatHistory(updatedMessages, currentChatId);

    } catch (error: any) {
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
    setSelectedImagesBase64([]);
  };

  // 履歴のダウンロード
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

  // 履歴のアップロード
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

  return (
    <div className="flex flex-1 h-[calc(100vh-64px)] mt-10 overflow-hidden">
      {/* サイドバー */}
      <div className="w-64 bg-white shadow-lg p-4 overflow-y-auto">
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
          {/* 選択画像のサムネイル表示 */}
          {selectedImagesBase64.length > 0 && (
            <div className="flex flex-wrap mb-4 gap-2">
              {selectedImagesBase64.map((imgBase64, i) => (
                <div key={i} className="relative inline-block">
                  <img
                    src={imgBase64}
                    alt="preview"
                    className="w-16 h-16 object-cover rounded border"
                  />
                  {/* 右上に×ボタン */}
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
