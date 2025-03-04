// frontend/src/components/Chat/ChatPage.tsx
import React, { useState, useRef, useEffect, ChangeEvent } from "react";
import { Message, ChatRequest, ChatHistory } from "../../types/apiTypes";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";
import { sendChunkedRequest } from "../../utils/ChunkedUpload";
import { FileData, FileType, processFile, convertFileDataForApi } from "../../utils/fileUtils";


const ChatPage: React.FC = () => {

  // ==========================
  //  State, Ref の定義
  // ==========================
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [chatHistories, setChatHistories] = useState<ChatHistory[]>([]);
  const messageContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // 各種ファイル用のステート
  const [selectedFiles, setSelectedFiles] = useState<FileData[]>([]);
  
  const [errorMessage, setErrorMessage] = useState<string>("");
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // --- 編集モード用 ---
  const [isEditMode, setIsEditMode] = useState<boolean>(false);
  const [backupMessages, setBackupMessages] = useState<Message[]>([]);
  // --- 拡大表示用画像 ---
  const [enlargedContent, setEnlargedContent] = useState<{ content: string, type: FileType } | null>(null);

  // IndexedDB用（ChatHistoryDB）
  function openChatHistoryDB(): Promise<IDBDatabase> {
    return indexedDBUtils.openDB("ChatHistoryDB", 1, (db) => {
      if (!db.objectStoreNames.contains("chatHistory")) {
        db.createObjectStore("chatHistory", { keyPath: "id" });
      }
    });
  }

  // ==========================
  //  IndexedDB 初期化とチャット履歴の読み込み
  // ==========================
  useEffect(() => {
    const initDB = async () => {
      try {
        await openChatHistoryDB();
        console.log("IndexedDB初期化成功");
        loadChatHistories();
      } catch (error) {
        console.error("IndexedDB初期化エラー:", error);
      }
    };

    initDB();
  }, []);

  // ==========================
  //  メッセージ表示エリアの自動スクロール
  // ==========================
  useEffect(() => {
    if (messageContainerRef.current) {
      messageContainerRef.current.scrollTop =
        messageContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // ==========================
  //  利用可能なAIモデル一覧の取得（サーバー設定から取得）
  // ==========================
  useEffect(() => {
    const config = Config.getServerConfig();
    if (config.MODELS) {
      const { options: modelsArr, defaultOption } = Config.parseOptionsWithDefault(config.MODELS);
      setModels(modelsArr.filter(m => m));
      setSelectedModel(defaultOption);
    }
  }, []);

  // ==========================
  //  ファイルアップロード関連定数
  // ==========================
  const MAX_IMAGES = Config.getServerConfig().MAX_IMAGES || 5;
  const MAX_LONG_EDGE = Config.getServerConfig().MAX_LONG_EDGE || 1568;
  const MAX_IMAGE_SIZE = Config.getServerConfig().MAX_IMAGE_SIZE || 5242880;
  // 送信時のプロンプトサイズ上限（バイト数）
  const MAX_PAYLOAD_SIZE = Config.getServerConfig().MAX_PAYLOAD_SIZE || 500000;

  // ==========================
  //  IndexedDB からチャット履歴を読み込み
  // ==========================
  const loadChatHistories = async () => {
    try {
      const db = await openChatHistoryDB();
      const transaction = db.transaction(["chatHistory"], "readonly");
      const store = transaction.objectStore("chatHistory");
      store.getAll().onsuccess = (e) => {
        const histories = (e.target as IDBRequest).result as ChatHistory[];
        const sortedHistories = histories
          .sort(
            (a, b) =>
              new Date(b.lastPromptDate).getTime() -
              new Date(a.lastPromptDate).getTime()
          )
          .slice(0, 30);
        setChatHistories(sortedHistories);
      };
    } catch (error) {
      console.error("履歴読み込みエラー:", error);
    }
  };

  // ==========================
  //  IndexedDB にチャット履歴を保存
  // ==========================
  const saveChatHistory = async (
    currentMessages: Message[],
    chatId: number | null
  ) => {
    if (currentMessages.length === 0) return;
    const newChatId = chatId ?? Date.now();
    if (!currentChatId) {
      setCurrentChatId(newChatId);
    }
    const historyItem: ChatHistory = {
      id: newChatId,
      title: currentMessages[0].content.slice(0, 10) + "...",
      messages: [...currentMessages],
      lastPromptDate: new Date().toISOString(),
    };
    try {
      const db = await openChatHistoryDB();
      const transaction = db.transaction(["chatHistory"], "readwrite");
      const store = transaction.objectStore("chatHistory");
      store.getAll().onsuccess = (e) => {
        const histories = (e.target as IDBRequest).result as ChatHistory[];
        const existingIndex = histories.findIndex((h) => h.id === chatId);
        let updatedHistories = [...histories];
        if (existingIndex !== -1) {
          updatedHistories[existingIndex] = {
            ...histories[existingIndex],
            messages: historyItem.messages,
            lastPromptDate: historyItem.lastPromptDate,
          };
        } else {
          updatedHistories.push(historyItem);
        }
        updatedHistories = updatedHistories
          .sort(
            (a, b) =>
              new Date(b.lastPromptDate).getTime() -
              new Date(a.lastPromptDate).getTime()
          )
          .slice(0, 30);
        store.clear().onsuccess = () => {
          updatedHistories.forEach((history) => store.add(history));
          setChatHistories(updatedHistories);
        };
      };
    } catch (error) {
      console.error("履歴保存エラー:", error);
    }
  };

  // ==========================
  //  履歴を復元
  // ==========================
  const restoreHistory = (history: ChatHistory) => {
    if (isEditMode) {
      setInput("");
      setSelectedFiles([]);
      setIsEditMode(false);
    }
    setCurrentChatId(history.id);
    setMessages(history.messages);
  };

  // ==========================
  //  チャットクリア
  // ==========================
  const clearChat = () => {
    setMessages([]);
    setCurrentChatId(null);
    setSelectedFiles([]);
    setInput("");
    setIsEditMode(false);
  };

  // ==========================
  //  ファイルアップロードハンドラー
  // ==========================
  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>, fileTypes: string[]) => {
    console.log(`[handleFileUpload] ${fileTypes.join('/')} ファイル選択イベント発生`);
    if (!e.target.files) return;
    
    const files = Array.from(e.target.files);
    const allowedCount = MAX_IMAGES - selectedFiles.length;
    
    if (files.length > allowedCount) {
      setErrorMessage(
        `一度にアップロードできるファイルは最大 ${MAX_IMAGES} 件です`
      );
      files.splice(allowedCount);
    }
    
    try {
      const fileDataPromises = files.map(file => 
        processFile(file, MAX_IMAGE_SIZE, MAX_LONG_EDGE, fileTypes)
      );
      
      const processedFiles = await Promise.all(fileDataPromises);
      let newFiles: FileData[] = [];
      
      // 処理結果が配列（PDFの複数ページ）かどうかを確認
      processedFiles.forEach(result => {
        if (Array.isArray(result)) {
          newFiles.push(...result);
        } else {
          newFiles.push(result);
        }
      });
      
      console.log(`[handleFileUpload] ファイル処理完了:`, newFiles);
      
      setSelectedFiles(prev => [...prev, ...newFiles]);
    } catch (error) {
      console.error(`[handleFileUpload] ファイルアップロードエラー:`, error);
      setErrorMessage("ファイルの処理中にエラーが発生しました");
    }
    
    // ファイル選択をリセット（同じファイルを連続で選択できるように）
    e.target.value = '';
  };

  // ==========================
  //  プロンプト編集
  // ==========================
  const handleEditPrompt = (index: number) => {
    if (isProcessing) return;
    const messageToEdit = messages[index];
    if (messageToEdit.role !== "user") return;
    
    setBackupMessages(messages);
    setInput(messageToEdit.content);
    
    // 古い形式の画像を新しい形式に変換
    const newFiles: FileData[] = [];
    
    if (messageToEdit.images && messageToEdit.images.length > 0) {
      messageToEdit.images.forEach((img, i) => {
        newFiles.push({
          id: `legacy_img_${i}`,
          name: `image_${i}.jpg`,
          type: FileType.IMAGE,
          content: img,
          size: 0, // サイズ不明
        });
      });
    }
    
    // 新形式のファイルがあれば追加
    if (messageToEdit.files && messageToEdit.files.length > 0) {
      newFiles.push(...messageToEdit.files);
    }
    
    setSelectedFiles(newFiles);
    setMessages(messages.slice(0, index));
    setIsEditMode(true);
  };

  const cancelEditMode = () => {
    if (backupMessages.length > 0) {
      setMessages(backupMessages);
      setBackupMessages([]);
    }
    setInput("");
    setSelectedFiles([]);
    setIsEditMode(false);
  };

  // ==========================
  //  メッセージ送信
  // ==========================
  const sendMessage = async () => {
    let backupInput = "";
    let backupFiles: FileData[] = [];
    let backupMsgs: Message[] = [];
    
    if (!input.trim() && selectedFiles.length === 0) return;
    if (isProcessing || !token) return;
    
    setErrorMessage("");
    
    try {
      setIsProcessing(true);
      backupInput = input;
      backupFiles = [...selectedFiles];
      backupMsgs = [...messages];

      // API用にファイルデータを変換
      const apiFileData = convertFileDataForApi(selectedFiles);
      
      const newUserMessage: Message = {
        role: "user",
        content: input.trim() || "[Files Uploaded]",
        images: apiFileData.images || [],
        files: selectedFiles,
        audioFiles: apiFileData.audioFiles || [],
        textFiles: apiFileData.textFiles || [],
      };

      let updatedMessages: Message[] = [...messages, newUserMessage];
      setMessages(updatedMessages);
      setInput("");
      setSelectedFiles([]);
      setIsEditMode(false);

      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      const chatRequest: ChatRequest = {
        messages: updatedMessages,
        model: selectedModel,
      };

      // 送信するリクエスト全体を JSON 化し、バイトサイズが上限を超えている場合はチャンク分割送信
      const jsonStr = JSON.stringify(chatRequest);
      const encoder = new TextEncoder();
      const chatRequestBytes = encoder.encode(jsonStr);

      // ① MAX_PAYLOAD_SIZEのログ出力
      console.log(`MAX_PAYLOAD_SIZE: ${MAX_PAYLOAD_SIZE} bytes`);
      // ② 送信前のプロンプトデータサイズのログ出力
      console.log(
        `送信前のプロンプトデータサイズ: ${chatRequestBytes.length} bytes`
      );

      let response: Response;
      if (chatRequestBytes.length > MAX_PAYLOAD_SIZE) {
        // ③ チャンク分割する旨のログ出力
        console.log(
          `プロンプトサイズ ${chatRequestBytes.length} bytes は上限 ${MAX_PAYLOAD_SIZE} bytes を超えているため、チャンク送信します`
        );
        response = await sendChunkedRequest(
          chatRequest,
          token,
          `${API_BASE_URL}/backend/chat`
        );
      } else {
        console.log("チャンクに分けずに送信します");
        response = await fetch(`${API_BASE_URL}/backend/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            Authorization: `Bearer ${token}`,
          },
          signal,
          body: jsonStr,
        });
      }

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      let assistantMessage = "";
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        updatedMessages = [
          ...updatedMessages,
          { role: "assistant", content: "" },
        ];
        setMessages(updatedMessages);

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const text = decoder.decode(value, { stream: true });
          assistantMessage += text;
          setMessages((msgs) => {
            const newMsgs = [...msgs];
            newMsgs[newMsgs.length - 1] = {
              role: "assistant",
              content: assistantMessage,
            };
            return newMsgs;
          });
        }
      }

      updatedMessages[updatedMessages.length - 1].content = assistantMessage;
      await saveChatHistory(updatedMessages, currentChatId);
    } catch (error: any) {
      if (error.name !== "AbortError") {
        console.error("メッセージ送信エラー:", error);
        setMessages(backupMsgs);
        setInput(backupInput);
        setSelectedFiles(backupFiles);
        setErrorMessage(
          error instanceof Error ? error.message : "不明なエラー"
        );
      }
    } finally {
      setIsProcessing(false);
      abortControllerRef.current = null;
    }
  };

  // ==========================
  //  キー押下による送信
  // ==========================
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ==========================
  //  送信停止（AbortController利用）
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
    const blob = new Blob([historyData], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
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
  const uploadHistory = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const content = e.target?.result as string;
        const uploadedHistories = JSON.parse(content) as ChatHistory[];
        const db = await openChatHistoryDB();
        const transaction = db.transaction(["chatHistory"], "readwrite");
        const store = transaction.objectStore("chatHistory");
        store.clear().onsuccess = () => {
          uploadedHistories.forEach((history) => store.add(history));
          setChatHistories(uploadedHistories);
        };
      } catch (error) {
        console.error("履歴アップロードエラー:", error);
      }
    };
    reader.readAsText(file);
  };
  
  // ==========================
  //  ファイル削除ハンドラー
  // ==========================
  const handleRemoveFile = (fileId: string) => {
    setSelectedFiles(prev => prev.filter(file => file.id !== fileId));
  };
  
  // ==========================
  //  ファイルプレビュー表示
  // ==========================
  const handleShowPreview = (file: FileData) => {
    if (file.type === FileType.IMAGE) {
      setEnlargedContent({ content: file.content, type: file.type });
    } else if (file.type === FileType.AUDIO) {
      // 音声ファイルはそのまま再生
      setEnlargedContent({ content: file.content, type: file.type });
    } else {
      // テキスト系はプレビューモーダルを表示
      setEnlargedContent({ content: file.content, type: file.type });
    }
  };

  // ==========================
  //  ファイルタイプに応じたアイコン表示
  // ==========================
  const getFileIcon = (type: FileType) => {
    switch (type) {
      case FileType.IMAGE:
        return "🖼️";
      case FileType.AUDIO:
        return "🔊";
      case FileType.TEXT:
        return "📄";
      case FileType.CSV:
        return "📊";
      case FileType.DOCX:
        return "📝";
      default:
        return "📎";
    }
  };

  // ==========================
  //  JSX の描画
  // ==========================
  return (
    <div className="flex flex-1 h-[calc(100vh-64px)] mt-2 overflow-hidden">
      {/* エラーポップアップ */}
      {errorMessage && (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-10">
          <div className="bg-white p-6 rounded shadow">
            <h2 className="text-xl font-semibold mb-4">エラー</h2>
            <p className="mb-4">{errorMessage}</p>
            <button
              onClick={() => setErrorMessage("")}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              閉じる
            </button>
          </div>
        </div>
      )}

      {/* サイドバー */}
      <div className="w-64 bg-gray-800 shadow-lg p-4 overflow-y-auto">
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-4 text-gray-100">
            モデル選択
          </h2>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
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
          onClick={clearChat}
          className="w-full mb-6 p-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg transition-colors"
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
        <div>
          <h2 className="text-lg font-semibold mb-4 text-gray-100">
            最近のチャット
          </h2>
          <div className="space-y-2">
            {chatHistories.map((history) => (
              <div
                key={history.id}
                onClick={() => restoreHistory(history)}
                className="p-2 hover:bg-gray-700 text-gray-100 rounded cursor-pointer transition-colors"
              >
                <div className="font-medium">{history.title}</div>
                <div className="text-sm text-gray-400">
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
                      onClick={() => handleEditPrompt(index)}
                      className="ml-2 text-sm text-gray-300 hover:text-gray-100"
                      title="このプロンプトを編集して再送信"
                    >
                      編集
                    </button>
                  </div>
                ) : (
                  <div>{message.content}</div>
                )}
                
                {/* 添付ファイルの表示（従来の画像対応） */}
                {message.images && message.images.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {message.images.map((img, i) => (
                      <div 
                        key={`legacy_img_${i}`}
                        onClick={() => setEnlargedContent({ content: img, type: FileType.IMAGE })}
                        className="relative cursor-pointer"
                      >
                        <img
                          src={img}
                          alt="Uploaded"
                          className="w-16 h-16 object-cover rounded border"
                        />
                      </div>
                    ))}
                  </div>
                )}
                
                {/* 新形式のファイル表示 */}
                {message.files && message.files.length > 0 && (
                  <div className="mt-2">
                    <div className="text-sm text-gray-300 mb-1">添付ファイル:</div>
                    <div className="flex flex-wrap gap-2">
                      {message.files.map((file) => (
                        <div 
                          key={file.id}
                          onClick={() => handleShowPreview(file)}
                          className="relative cursor-pointer"
                        >
                          {file.type === FileType.IMAGE ? (
                            <img 
                              src={file.content} 
                              alt={file.name}
                              className="w-16 h-16 object-cover rounded border" 
                            />
                          ) : (
                            <div className="p-2 bg-gray-700 rounded border border-gray-600 flex items-center">
                              <span className="mr-2">{getFileIcon(file.type)}</span>
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

        {/* 入力エリア */}
        <div className="border-t border-gray-700 p-4 bg-gray-800">
          {isEditMode && (
            <div className="mb-2 p-2 bg-yellow-200 text-yellow-800 rounded flex justify-between items-center">
              <span>※ 現在、プロンプトのやり直しモードです</span>
              <button
                onClick={cancelEditMode}
                className="text-sm text-red-600 hover:underline"
              >
                キャンセル
              </button>
            </div>
          )}
          
          {/* 選択済みファイルのプレビュー表示 */}
          {selectedFiles.length > 0 && (
            <div className="flex flex-wrap mb-4 gap-2">
              {selectedFiles.map((file) => (
                <div key={file.id} className="relative inline-block">
                  {file.type === FileType.IMAGE ? (
                    <img
                      src={file.content}
                      alt={file.name}
                      onClick={() => handleShowPreview(file)}
                      className="w-16 h-16 object-cover rounded border cursor-pointer"
                    />
                  ) : (
                    <div 
                      className="w-16 h-16 bg-gray-700 flex flex-col items-center justify-center rounded border cursor-pointer"
                      onClick={() => handleShowPreview(file)}
                    >
                      <div>{getFileIcon(file.type)}</div>
                      <div className="text-xs truncate w-full text-center px-1">
                        {file.name.length > 8 ? file.name.substring(0, 8) + '...' : file.name}
                      </div>
                    </div>
                  )}
                  <button
                    className="absolute top-0 right-0 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center"
                    onClick={() => handleRemoveFile(file.id)}
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
              className="flex-1 p-2 bg-gray-900 border border-gray-700 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-100"
              placeholder="メッセージを入力..."
              rows={2}
              disabled={isProcessing}
            />
            
            {/* ファイル添付ボタングループ */}
            <div className="flex flex-col space-y-2">
              {/* 画像ボタン */}
              <label className="flex items-center justify-center px-4 py-1 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg cursor-pointer">
                <span>🖼️</span>
                <input
                  type="file"
                  accept="image/*,.pdf"
                  multiple
                  className="hidden"
                  onChange={(e) => handleFileUpload(e, ['image/*', 'application/pdf'])}
                  disabled={isProcessing}
                />
              </label>
              
              {/* 音声ボタン */}
              <label className="flex items-center justify-center px-4 py-1 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg cursor-pointer">
                <span>🔊</span>
                <input
                  type="file"
                  accept="audio/*"
                  multiple
                  className="hidden"
                  onChange={(e) => handleFileUpload(e, ['audio/*'])}
                  disabled={isProcessing}
                />
              </label>
              
              {/* テキストボタン */}
              <label className="flex items-center justify-center px-4 py-1 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg cursor-pointer">
                <span>📄</span>
                <input
                  type="file"
                  accept=".txt,.docx,.csv,.pdf"
                  multiple
                  className="hidden"
                  onChange={(e) => handleFileUpload(e, ['.txt', '.docx', '.csv', '.pdf'])}
                  disabled={isProcessing}
                />
              </label>
            </div>
            
            {/* 送信ボタン */}
            <button
              onClick={isProcessing ? stopGeneration : sendMessage}
              className={`px-4 py-2 rounded-lg ${
                isProcessing
                  ? "bg-red-900 hover:bg-red-800"
                  : "bg-blue-900 hover:bg-blue-800"
              } text-gray-100 transition-colors`}
            >
              {isProcessing ? "停止" : "送信"}
            </button>
          </div>
        </div>
      </div>

      {/* コンテンツ拡大表示用モーダル */}
      {enlargedContent && (
        <div
          className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-75 z-50"
          onClick={() => setEnlargedContent(null)}
        >
          <div className="relative max-w-4xl max-h-[90vh] overflow-auto bg-gray-800 rounded-lg p-4">
            <button
              className="absolute top-2 right-2 text-white text-2xl font-bold"
              onClick={() => setEnlargedContent(null)}
            >
              ×
            </button>
            
            {enlargedContent.type === FileType.IMAGE ? (
              <img
                src={enlargedContent.content}
                alt="Enlarged content"
                className="max-h-[80vh]"
                onClick={(e) => e.stopPropagation()}
              />
            ) : enlargedContent.type === FileType.AUDIO ? (
              <audio
                src={enlargedContent.content}
                controls
                className="w-full"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <div 
                className="bg-white text-black p-4 rounded max-h-[80vh] overflow-auto"
                onClick={(e) => e.stopPropagation()}
              >
                <pre className="whitespace-pre-wrap">{enlargedContent.content}</pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatPage;