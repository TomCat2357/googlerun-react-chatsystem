// frontend/src/components/Chat/ChatPage.tsx
import React, { useState, useRef, useEffect, ChangeEvent } from "react";
import { Message, ChatRequest, ChatHistory } from "../../types/apiTypes";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";
import { sendChunkedRequest } from "../../utils/ChunkedUpload";
import { FileData } from "../../utils/fileUtils";
import ChatSidebar from "./ChatSidebar";
import ChatMessages from "./ChatMessages";
import ChatInput from "./ChatInput";
import FilePreview from "./FilePreview";
import FileViewerModal from "./FileViewerModal";
import ErrorModal from "./ErrorModal";

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
  const abortControllerRef = useRef<AbortController | null>(null);

  // ファイル関連の状態
  const [selectedFiles, setSelectedFiles] = useState<FileData[]>([]);
  const [enlargedContent, setEnlargedContent] = useState<{
    content: string;
    mimeType: string;
  } | null>(null);

  const [errorMessage, setErrorMessage] = useState<string>("");
  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;

  // 編集モード用の状態
  const [isEditMode, setIsEditMode] = useState<boolean>(false);
  const [backupMessages, setBackupMessages] = useState<Message[]>([]);

  // ==========================
  //  設定の読み込み
  // ==========================
  const MAX_IMAGES = Config.getServerConfig().MAX_IMAGES || 5;
  const MAX_AUDIO_FILES = Config.getServerConfig().MAX_AUDIO_FILES || 1;
  const MAX_TEXT_FILES = Config.getServerConfig().MAX_TEXT_FILES || 5;
  const MAX_LONG_EDGE = Config.getServerConfig().MAX_LONG_EDGE || 1568;
  const MAX_IMAGE_SIZE = Config.getServerConfig().MAX_IMAGE_SIZE || 5242880;
  const MAX_PAYLOAD_SIZE = Config.getServerConfig().MAX_PAYLOAD_SIZE || 500000;

  // ==========================
  //  初期化処理
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
  //  利用可能なAIモデル一覧の取得
  // ==========================
  useEffect(() => {
    const config = Config.getServerConfig();
    if (config.MODELS) {
      const { options: modelsArr, defaultOption } =
        Config.parseOptionsWithDefault(config.MODELS);
      setModels(modelsArr.filter((m) => m));
      setSelectedModel(defaultOption);
    }
  }, []);

  // ==========================
  //  IndexedDB関連の処理
  // ==========================
  function openChatHistoryDB(): Promise<IDBDatabase> {
    return indexedDBUtils.openDB("ChatHistoryDB", 1, (db) => {
      if (!db.objectStoreNames.contains("chatHistory")) {
        db.createObjectStore("chatHistory", { keyPath: "id" });
      }
    });
  }

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
  //  サイドバー関連の処理
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

  const clearChat = () => {
    setMessages([]);
    setCurrentChatId(null);
    setSelectedFiles([]);
    setInput("");
    setIsEditMode(false);
  };

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
  //  エディットモード関連の処理
  // ==========================
  const handleEditPrompt = (index: number) => {
    if (isProcessing) return;
    const messageToEdit = messages[index];
    if (messageToEdit.role !== "user") return;

    setBackupMessages(messages);
    setInput(messageToEdit.content);

    // ファイルデータの処理
    const newFiles: FileData[] = [];

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
  //  ファイル処理関連の関数を他のコンポーネントに渡す
  // ==========================
  const handleRemoveFile = (fileId: string) => {
    setSelectedFiles(selectedFiles.filter((file) => file.id !== fileId));
  };

  const handleViewFile = (content: string, mimeType: string) => {
    setEnlargedContent({ content, mimeType });
  };

  const handleCloseFileViewer = () => {
    setEnlargedContent(null);
  };

  const addFiles = (newFiles: FileData[]) => {
    setSelectedFiles([...selectedFiles, ...newFiles]);
  };

  // ==========================
  //  メッセージ送信処理
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

      const newUserMessage: Message = {
        role: "user",
        content: input.trim() || "[Files Uploaded]",
        files: selectedFiles
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

      // 送信前にログ出力する処理を追加
      const logMessages = updatedMessages.map(msg => {
        // filesがある場合のみ処理
        if (msg.files && msg.files.length > 0) {
          return {
            ...msg,
            files: msg.files.map(file => ({
              ...file,
              content: file.content.substring(0, 10) + '...' // 最初の10文字だけ表示
            }))
          };
        }
        return msg;
      });
      
      console.log('バックエンドに送信するチャットデータ:', {
        ...chatRequest,
        messages: logMessages
      });

      // 送信データサイズチェック
      const jsonStr = JSON.stringify(chatRequest);
      const encoder = new TextEncoder();
      const chatRequestBytes = encoder.encode(jsonStr);

      console.log(`MAX_PAYLOAD_SIZE: ${MAX_PAYLOAD_SIZE} bytes`);
      console.log(`送信前のプロンプトデータサイズ: ${chatRequestBytes.length} bytes`);

      let response: Response;
      if (chatRequestBytes.length > MAX_PAYLOAD_SIZE) {
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
  //  送信停止（AbortController利用）
  // ==========================
  const stopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsProcessing(false);
    }
  };

  // ==========================
  //  JSX の描画
  // ==========================
  return (
    <div className="flex flex-1 h-[calc(100vh-64px)] mt-2 overflow-hidden">
      {/* エラーモーダル */}
      {errorMessage && (
        <ErrorModal
          message={errorMessage}
          onClose={() => setErrorMessage("")}
        />
      )}

      {/* サイドバー */}
      <ChatSidebar
        models={models}
        selectedModel={selectedModel}
        chatHistories={chatHistories}
        onModelChange={setSelectedModel}
        onClearChat={clearChat}
        onRestoreHistory={restoreHistory}
        onDownloadHistory={downloadHistory}
        onUploadHistory={uploadHistory}
      />

      {/* メインチャットエリア */}
      <div className="flex-1 flex flex-col h-full">
        {/* メッセージ表示エリア */}
        <ChatMessages
          messages={messages}
          onEditPrompt={handleEditPrompt}
          onViewFile={handleViewFile}
        />

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
            <FilePreview
              files={selectedFiles}
              onRemoveFile={handleRemoveFile}
              onViewFile={handleViewFile}
            />
          )}

          {/* チャット入力エリア */}
          <ChatInput
            input={input}
            setInput={setInput}
            isProcessing={isProcessing}
            selectedFiles={selectedFiles}
            addFiles={addFiles}
            sendMessage={sendMessage}
            stopGeneration={stopGeneration}
            setErrorMessage={setErrorMessage}
            maxLimits={{
              MAX_IMAGES,
              MAX_AUDIO_FILES,
              MAX_TEXT_FILES,
              MAX_IMAGE_SIZE,
              MAX_LONG_EDGE
            }}
          />
        </div>
      </div>

      {/* ファイル拡大表示用モーダル */}
      {enlargedContent && (
        <FileViewerModal
          content={enlargedContent.content}
          mimeType={enlargedContent.mimeType}
          onClose={handleCloseFileViewer}
        />
      )}
    </div>
  );
};

export default ChatPage;