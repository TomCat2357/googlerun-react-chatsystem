import React, { useState, useRef, useEffect } from 'react';
import { Message, ChatRequest } from '../../types/apiTypes';
import { useAuth } from '../../contexts/AuthContext';

export const ChatContainer: React.FC = () => {
  const { currentUser } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const messageContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [token, setToken] = useState<string>('');

  useEffect(() => {
    // currentUser が変化したらトークンを取得
    const fetchToken = async () => {
      if (currentUser) {
        const t = await currentUser.getIdToken();
        setToken(t);
      }
    };
    fetchToken();
  }, [currentUser]);

  useEffect(() => {
    // メッセージが追加されたら自動スクロール
    if (messageContainerRef.current) {
      messageContainerRef.current.scrollTop = messageContainerRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    const fetchToken = async () => {
      if (currentUser) {
        const t = await currentUser.getIdToken();
        console.log('🔑 トークン取得:', t.substring(0, 20) + '...');
        setToken(t);
      }
    };
    fetchToken();
  }, [currentUser]);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        if (!token) {
          console.log('🔒 トークンが存在しません');
          return;
        }
        console.log('📋 モデルリスト取得開始');
        console.log('🔑 使用するトークン:', token.substring(0, 20) + '...');
        
        const response = await fetch('http://localhost:8080/app/models', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        });
        
        console.log('📡 レスポンスステータス:', response.status);
        const responseText = await response.text();
        console.log('📝 生レスポンス:', responseText);
        
        // JSONとして解析を試みる
        const data = JSON.parse(responseText);
        console.log('📋 取得したモデルリスト:', data.models);
        
        if (Array.isArray(data.models)) {
          setModels(data.models);
          setSelectedModel(data.models[0] || '');
        }
      } catch (err) {
        console.error('❌ モデルリスト取得エラー:', err);
        console.error('❌ エラーの詳細:', {
          name: err.name,
          message: err.message,
          stack: err.stack
        });
      }
    };
    fetchModels();
  }, 
  //[token],
  [currentUser],
);

  const sendMessage = async () => {
    if (!input.trim() || isProcessing || !token) return;

    try {
      console.log('💬 メッセージ送信開始');
      console.log('📤 送信内容:', input);
      console.log('🤖 選択中のモデル:', selectedModel);
      
      setIsProcessing(true);
      const newUserMessage: Message = { role: 'user', content: input };
      setMessages(prev => [...prev, newUserMessage]);
      setInput('');

      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      const chatRequest: ChatRequest = {
        messages: [...messages, newUserMessage],
        model: selectedModel || ''
      };

      // Authorization ヘッダーを追加してクッキー非使用でリクエスト
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
          if (done) {
            console.log('✅ ストリーミング完了');
            break;
          }
          const text = decoder.decode(value, { stream: true });
          console.log('📥 受信チャンク:', text);
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
      console.error('❌ エラー詳細:', error);
      if (error.name !== 'AbortError') {
        console.log('🚫 通常エラー発生');
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: 'エラーが発生しました: ' + (error instanceof Error ? error.message : 'Unknown error')
          }
        ]);
      } else {
        console.log('⚠️ 生成停止');
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
      console.log('🛑 生成停止リクエスト');
      abortControllerRef.current.abort();
      setIsProcessing(false);
    }
  };
  

  return (
    <div className="flex flex-col h-full bg-white rounded-lg shadow">
      <div ref={messageContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`p-2 rounded-lg ${
              message.role === 'user'
                ? 'bg-blue-100 ml-auto max-w-[80%]'
                : 'bg-gray-100 mr-auto max-w-[80%]'
            }`}
          >
            {message.content}
          </div>
        ))}
      </div>

      <div className="p-2">
        <label className="mr-2">モデル:</label>
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="p-1 border rounded"
        >
          {models.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      <div className="border-t p-4">
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
  );
};
