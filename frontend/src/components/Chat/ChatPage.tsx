// src/pages/chatpage.tsx
import React, { useState, useRef, useEffect, ChangeEvent } from "react";
import { Message, ChatRequest, ChatHistory } from "../../types/apiTypes";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";

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
  const [selectedImagesBase64, setSelectedImagesBase64] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // --- 編集モード用 ---
  const [isEditMode, setIsEditMode] = useState<boolean>(false);
  const [backupMessages, setBackupMessages] = useState<Message[]>([]);
  // --- 拡大表示用画像 ---
  const [enlargedImage, setEnlargedImage] = useState<string | null>(null);

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
        const response = await fetch(`${API_BASE_URL}/backend/models`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
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
        console.error("モデル一覧取得エラー:", error);
      }
    };
    fetchModels();
  }, [token]);

  // ==========================
  //  画像アップロード関連定数
  // ==========================
  const MAX_IMAGES = Config.MAX_IMAGES;
  const MAX_LONG_EDGE = Config.MAX_LONG_EDGE;
  const MAX_IMAGE_SIZE = Config.MAX_IMAGE_SIZE;

  /**
   * processImageFile
   *
   * 画像ファイルを読み込み、リサイズ・再圧縮後の dataURL を返す
   */
  const processImageFile = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      console.log("[processImageFile] 処理開始：", file.name);
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          const dataUrl = event.target.result as string;
          const image = new Image();
          image.onload = () => {
            console.log("[processImageFile] 画像読み込み完了：", file.name);
            let { naturalWidth: width, naturalHeight: height } = image;
            console.log(`[processImageFile] 元サイズ: ${width}x${height}`);
            const longEdge = Math.max(width, height);
            let scale = 1;
            if (longEdge > MAX_LONG_EDGE) {
              scale = MAX_LONG_EDGE / longEdge;
              width = Math.floor(width * scale);
              height = Math.floor(height * scale);
              console.log(`[processImageFile] リサイズ実施：新サイズ ${width}x${height}`);
            } else {
              console.log("[processImageFile] リサイズ不要");
            }
            const canvas = document.createElement("canvas");
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext("2d");
            if (!ctx) {
              reject(new Error("キャンバスの取得に失敗しました"));
              return;
            }
            ctx.drawImage(image, 0, 0, width, height);

            let quality = 0.85;
            const minQuality = 0.3;
            const processCanvas = () => {
              const newDataUrl = canvas.toDataURL("image/jpeg", quality);
              const arr = newDataUrl.split(",");
              const byteString = atob(arr[1]);
              const buffer = new ArrayBuffer(byteString.length);
              const intArray = new Uint8Array(buffer);
              for (let i = 0; i < byteString.length; i++) {
                intArray[i] = byteString.charCodeAt(i);
              }
              const blob = new Blob([buffer], { type: "image/jpeg" });
              console.log(`[processImageFile] 現在の品質 ${quality}, Blobサイズ: ${blob.size} bytes`);
              if (blob.size > MAX_IMAGE_SIZE && quality > minQuality) {
                quality -= 0.1;
                console.log(`[processImageFile] サイズ超過のため再圧縮：新品質 ${quality}`);
                processCanvas();
              } else {
                console.log("[processImageFile] 画像処理完了");
                resolve(newDataUrl);
              }
            };
            processCanvas();
          };
          image.onerror = () => {
            console.error("[processImageFile] 画像読み込みエラー", file.name);
            reject(new Error("画像読み込みエラー"));
          };
          image.src = dataUrl;
        } else {
          reject(new Error("Failed to read file"));
        }
      };
      reader.onerror = () => {
        console.error("[processImageFile] ファイル読み込みエラー", file.name);
        reject(new Error("ファイル読み込みエラー"));
      };
      reader.readAsDataURL(file);
    });
  };

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
          .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
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
  const saveChatHistory = async (currentMessages: Message[], chatId: number | null) => {
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
          .sort((a, b) => new Date(b.lastPromptDate).getTime() - new Date(a.lastPromptDate).getTime())
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
      setSelectedImagesBase64([]);
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
    setSelectedImagesBase64([]);
    setInput("");
    setIsEditMode(false);
  };

  // ==========================
  //  画像アップロードハンドラー
  // ==========================
  const handleImageUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    console.log("[handleImageUpload] ファイル選択イベント発生");
    if (!e.target.files) return;
    const files = Array.from(e.target.files);
    const allowedCount = MAX_IMAGES - selectedImagesBase64.length;
    if (files.length > allowedCount) {
      setErrorMessage(`一度にアップロードできる画像は最大 ${MAX_IMAGES} 枚です`);
      files.splice(allowedCount);
    }
    const promises = files.map((file) => processImageFile(file));
    try {
      const newBase64s = await Promise.all(promises);
      console.log("[handleImageUpload] 画像処理完了:", newBase64s);
      setSelectedImagesBase64((prev) => [...prev, ...newBase64s]);
    } catch (error) {
      console.error("[handleImageUpload] 画像アップロードエラー:", error);
      setErrorMessage("画像の処理中にエラーが発生しました");
    }
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
    if (messageToEdit.images && messageToEdit.images.length > 0) {
      setSelectedImagesBase64([...messageToEdit.images]);
    } else {
      setSelectedImagesBase64([]);
    }
    setMessages(messages.slice(0, index));
    setIsEditMode(true);
  };

  const cancelEditMode = () => {
    if (backupMessages.length > 0) {
      setMessages(backupMessages);
      setBackupMessages([]);
    }
    setInput("");
    setSelectedImagesBase64([]);
    setIsEditMode(false);
  };

  // ==========================
  //  メッセージ送信
  // ==========================
  const sendMessage = async () => {
    let backupInput = "";
    let backupImages: string[] = [];
    let backupMsgs: Message[] = [];
    if (!input.trim() && selectedImagesBase64.length === 0) return;
    if (isProcessing || !token) return;
    setErrorMessage("");
    try {
      setIsProcessing(true);
      backupInput = input;
      backupImages = [...selectedImagesBase64];
      backupMsgs = [...messages];

      const newUserMessage: Message = {
        role: "user",
        content: input.trim() || "[Images Uploaded]",
        images: selectedImagesBase64.length > 0 ? [...selectedImagesBase64] : [],
      };

      let updatedMessages: Message[] = [...messages, newUserMessage];
      setMessages(updatedMessages);
      setInput("");
      setSelectedImagesBase64([]);
      setIsEditMode(false);

      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      const chatRequest: ChatRequest = {
        messages: updatedMessages,
        model: selectedModel,
      };

      const response = await fetch(`${API_BASE_URL}/backend/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          Authorization: `Bearer ${token}`,
        },
        signal,
        body: JSON.stringify(chatRequest),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      let assistantMessage = "";
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        updatedMessages = [...updatedMessages, { role: "assistant", content: "" }];
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
        setSelectedImagesBase64(backupImages);
        setErrorMessage(error instanceof Error ? error.message : "不明なエラー");
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
          <h2 className="text-lg font-semibold mb-4 text-gray-100">モデル選択</h2>
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
            <input type="file" accept=".json" onChange={uploadHistory} className="hidden" />
            <span className="block p-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg transition-colors text-center cursor-pointer">
              履歴読込
            </span>
          </label>
        </div>
        <div>
          <h2 className="text-lg font-semibold mb-4 text-gray-100">最近のチャット</h2>
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
        <div ref={messageContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-900">
          {messages.map((message, index) => (
            <div key={index} className={`max-w-[80%] ${message.role === "user" ? "ml-auto" : "mr-auto"}`}>
              <div className={`p-4 rounded-lg ${message.role === "user" ? "bg-blue-900 text-gray-100" : "bg-gray-800 border border-gray-700 text-gray-100"}`}>
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
                {message.images && message.images.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {message.images.map((img, i) => (
                      <img
                        key={i}
                        src={img}
                        alt="Uploaded"
                        onClick={() => setEnlargedImage(img)}
                        className="max-w-xs rounded border cursor-pointer"
                      />
                    ))}
                  </div>
                )}
              </div>
              <div className={`text-xs text-gray-400 mt-1 ${message.role === "user" ? "text-right" : "text-left"}`}>
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
              <button onClick={cancelEditMode} className="text-sm text-red-600 hover:underline">
                キャンセル
              </button>
            </div>
          )}
          {selectedImagesBase64.length > 0 && (
            <div className="flex flex-wrap mb-4 gap-2">
              {selectedImagesBase64.map((imgBase64, i) => (
                <div key={i} className="relative inline-block">
                  <img
                    src={imgBase64}
                    alt="preview"
                    onClick={() => setEnlargedImage(imgBase64)}
                    className="w-16 h-16 object-cover rounded border cursor-pointer"
                  />
                  <button
                    className="absolute top-0 right-0 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center"
                    onClick={() =>
                      setSelectedImagesBase64((prev) => prev.filter((_, index) => index !== i))
                    }
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
            <label className="flex items-center justify-center px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-100 rounded-lg cursor-pointer">
              画像選択
              <input type="file" accept="image/*" multiple className="hidden" onChange={handleImageUpload} disabled={isProcessing} />
            </label>
            <button onClick={isProcessing ? stopGeneration : sendMessage} className={`px-4 py-2 rounded-lg ${isProcessing ? "bg-red-900 hover:bg-red-800" : "bg-blue-900 hover:bg-blue-800"} text-gray-100 transition-colors`}>
              {isProcessing ? "停止" : "送信"}
            </button>
          </div>
        </div>
      </div>

      {/* 拡大表示用モーダル */}
      {enlargedImage && (
        <div
          className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-75 z-50"
          onClick={() => setEnlargedImage(null)}
        >
          <div className="relative">
            <button className="absolute top-0 right-0 m-2 text-white text-2xl font-bold" onClick={() => setEnlargedImage(null)}>
              ×
            </button>
            <img src={enlargedImage} alt="Enlarged" className="max-h-screen max-w-full" onClick={(e) => e.stopPropagation()} />
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatPage;
