// frontend/src/components/Chat/ChatPage.tsx
import React, { useEffect, useState } from "react";
import { useToken } from "../../hooks/useToken";
import { useChatOperations } from "../../hooks/useChatOperations";
import { useChatHistory } from "../../hooks/useChatHistory";
import { useFileUpload } from "../../hooks/useFileUpload";
import { useErrorHandler } from "../../hooks/useErrorHandler";
import { FileData } from "../../types/apiTypes";
import * as Config from "../../config";

import ChatSidebar from "./ChatSidebar";
import ChatMessages from "./ChatMessages";
import ChatInput from "./ChatInput";
import FilePreview from "./FilePreview";
import FileViewerModal from "./FileViewerModal";
import ErrorModal from "./ErrorModal";

const ChatPage: React.FC = () => {
  const token = useToken();
  const { error: globalError, clearError } = useErrorHandler();
  
  // チャット操作フック
  const {
    messages,
    input,
    models,
    selectedModel,
    isProcessing,
    isEditMode,
    setInput,
    setSelectedModel,
    loadModels,
    sendMessage,
    cancelMessage,
    clearMessages,
    loadMessages,
    startEditMode,
    saveEditMode,
    cancelEditMode,
    deleteMessage,
    editMessage,
    deleteMessagesFromIndex,
    regenerateLastMessage,
  } = useChatOperations();

  // チャット履歴フック
  const {
    chatHistories,
    currentChatId,
    isLoading: isHistoryLoading,
    setCurrentChatId,
    createNewChat,
    saveChatHistory,
    deleteChatHistory,
    loadChatHistory,
    updateChatTitle,
    clearAllChatHistories,
    exportChatHistory,
    importChatHistory,
  } = useChatHistory();

  // ファイルアップロードフック
  const {
    files: selectedFiles,
    isUploading,
    handleFileSelect,
    removeFile,
    clearFiles,
    fileInputRef,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
  } = useFileUpload({
    allowedTypes: ['image/*', 'audio/*', '.txt', '.csv', '.pdf', '.docx'],
    maxFiles: 10,
    maxSize: 50 * 1024 * 1024, // 50MB
    maxImageSize: 20 * 1024 * 1024, // 20MB
    enableDragDrop: true,
    extractMetadata: true,
  });

  // ファイルビューワー関連
  const [enlargedContent, setEnlargedContent] = useState<{
    content: string;
    mimeType: string;
  } | null>(null);

  // 設定
  const MAX_IMAGES = Config.getServerConfig().MAX_IMAGES || 5;
  const MAX_AUDIO_FILES = Config.getServerConfig().MAX_AUDIO_FILES || 1;
  const MAX_TEXT_FILES = Config.getServerConfig().MAX_TEXT_FILES || 5;
  const MAX_IMAGE_SIZE = Config.getServerConfig().MAX_IMAGE_SIZE || 20 * 1024 * 1024;
  const MAX_LONG_EDGE = Config.getServerConfig().MAX_LONG_EDGE || 3008;

  /**
   * 初期化処理
   */
  useEffect(() => {
    if (token) {
      loadModels();
    }
  }, [token, loadModels]);

  /**
   * 新しいチャットを開始
   */
  const handleNewChat = async () => {
    try {
      await createNewChat('新しいチャット', selectedModel);
      clearMessages();
      clearFiles();
      clearError();
    } catch (error) {
      console.error('新しいチャット作成エラー:', error);
    }
  };

  /**
   * チャット履歴を選択
   */
  const handleSelectHistory = async (chatId: number) => {
    try {
      const messages = await loadChatHistory(chatId);
      loadMessages(messages);
      clearFiles();
      clearError();
    } catch (error) {
      console.error('チャット履歴読み込みエラー:', error);
    }
  };

  /**
   * チャット履歴を削除
   */
  const handleDeleteHistory = async (chatId: number) => {
    try {
      await deleteChatHistory(chatId);
      
      if (currentChatId === chatId) {
        clearMessages();
        clearFiles();
      }
    } catch (error) {
      console.error('チャット履歴削除エラー:', error);
    }
  };

  /**
   * チャット履歴をダウンロード
   */
  const handleDownloadHistory = async () => {
    if (!currentChatId) return;

    try {
      const historyJson = await exportChatHistory(currentChatId);
      const blob = new Blob([historyJson], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chat_history_${currentChatId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('チャット履歴ダウンロードエラー:', error);
    }
  };

  /**
   * チャット履歴をアップロード
   */
  const handleUploadHistory = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const newChatId = await importChatHistory(text);
      await handleSelectHistory(newChatId);
    } catch (error) {
      console.error('チャット履歴アップロードエラー:', error);
    }

    event.target.value = '';
  };

  /**
   * メッセージ送信
   */
  const handleSendMessage = async () => {
    if ((!input.trim() && selectedFiles.length === 0) || isProcessing) return;

    await sendMessage(input, selectedFiles);
    clearFiles();
  };

  /**
   * ファイルを追加
   */
  const handleAddFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    handleFileSelect(event);
  };

  /**
   * ファイルを削除
   */
  const handleRemoveFile = (fileId: string) => {
    const index = selectedFiles.findIndex(file => file.id === fileId);
    if (index >= 0) {
      removeFile(index);
    }
  };

  /**
   * ファイルを表示
   */
  const handleViewFile = (content: string, mimeType: string) => {
    setEnlargedContent({ content, mimeType });
  };

  /**
   * プロンプト編集
   */
  const handleEditPrompt = (index: number, messageContent: string) => {
    if (!isEditMode) {
      startEditMode();
    }
    
    // 指定されたメッセージ以降を削除
    deleteMessagesFromIndex(index);
    
    // 入力欄に内容を設定
    setInput(messageContent);
  };

  /**
   * 生成停止
   */
  const handleStopGeneration = () => {
    cancelMessage();
  };

  if (!token) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-gray-400 mb-4">チャットを利用するにはログインが必要です</p>
        </div>
      </div>
    );
  }

  return (
    <div 
      className="flex h-full bg-gray-900 text-white"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* サイドバー */}
      <ChatSidebar
        models={models}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        chatHistories={chatHistories}
        currentChatId={currentChatId}
        onNewChat={handleNewChat}
        onSelectHistory={handleSelectHistory}
        onClearAll={clearAllChatHistories}
        onDownloadHistory={handleDownloadHistory}
        onUploadHistory={handleUploadHistory}
        onDeleteHistory={handleDeleteHistory}
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
          {/* 編集モード表示 */}
          {isEditMode && (
            <div className="mb-2 p-2 bg-yellow-200 text-yellow-800 rounded flex justify-between items-center">
              <span>※ 現在、プロンプトのやり直しモードです</span>
              <div className="space-x-2">
                <button
                  onClick={saveEditMode}
                  className="text-sm text-green-600 hover:underline"
                >
                  保存
                </button>
                <button
                  onClick={cancelEditMode}
                  className="text-sm text-red-600 hover:underline"
                >
                  キャンセル
                </button>
              </div>
            </div>
          )}

          {/* 選択済みファイルのプレビュー */}
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
            isProcessing={isProcessing || isUploading}
            selectedFiles={selectedFiles}
            addFiles={handleAddFiles}
            sendMessage={handleSendMessage}
            stopGeneration={handleStopGeneration}
            setErrorMessage={() => {}} // エラーは統一的に処理
            maxLimits={{
              MAX_IMAGES,
              MAX_AUDIO_FILES,
              MAX_TEXT_FILES,
              MAX_IMAGE_SIZE,
              MAX_LONG_EDGE,
            }}
          />
        </div>
      </div>

      {/* ファイルビューワーモーダル */}
      {enlargedContent && (
        <FileViewerModal
          content={enlargedContent.content}
          mimeType={enlargedContent.mimeType}
          onClose={() => setEnlargedContent(null)}
        />
      )}

      {/* エラーモーダル */}
      {globalError && (
        <ErrorModal
          message={globalError}
          onClose={clearError}
        />
      )}

      {/* 隠しファイル入力 */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,audio/*,.txt,.csv,.pdf,.docx"
        onChange={handleAddFiles}
        style={{ display: 'none' }}
      />
    </div>
  );
};

export default ChatPage;