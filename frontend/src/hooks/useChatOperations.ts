import { useState, useCallback, useRef } from 'react';
import { Message, ChatRequest } from '../types/apiTypes';
import { FileData } from '../utils/fileUtils';
import { useApiCall } from './useApiCall';
import { useErrorHandler } from './useErrorHandler';
import { useLoadingState } from './useLoadingState';
import { useChatHistory } from './useChatHistory';
import * as Config from '../config';

/**
 * チャット操作フック
 * チャットメッセージの送信、ストリーミング、モデル管理などを統括
 */
export const useChatOperations = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [isEditMode, setIsEditMode] = useState(false);
  const [backupMessages, setBackupMessages] = useState<Message[]>([]);

  const abortControllerRef = useRef<AbortController | null>(null);
  
  const { streamingApiCall, apiCall } = useApiCall();
  const { handleError, clearError } = useErrorHandler();
  const { isLoading: isProcessing, withLoading } = useLoadingState();
  const { currentChatId, saveChatHistory } = useChatHistory();

  const API_BASE_URL = Config.API_BASE_URL;

  /**
   * 利用可能なモデル一覧を取得
   */
  const loadModels = useCallback(async () => {
    try {
      const response = await apiCall<{ models: string[] }>(`${API_BASE_URL}/backend/models`);
      setModels(response.data.models || []);
      
      // 最初のモデルを選択
      if (response.data.models && response.data.models.length > 0 && !selectedModel) {
        setSelectedModel(response.data.models[0]);
      }
    } catch (error) {
      handleError(error, 'モデル一覧取得');
    }
  }, [apiCall, selectedModel, API_BASE_URL, handleError]);

  /**
   * チャットメッセージを送信（ストリーミング）
   */
  const sendMessage = useCallback(async (
    messageContent: string,
    selectedFiles: FileData[] = []
  ) => {
    if (!messageContent.trim() && selectedFiles.length === 0) {
      handleError(new Error('メッセージまたはファイルを入力してください'), 'メッセージ送信');
      return;
    }

    if (!selectedModel) {
      handleError(new Error('モデルを選択してください'), 'メッセージ送信');
      return;
    }

    // AbortControllerを作成
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    return withLoading(async () => {
      try {
        clearError();

        // ユーザーメッセージを追加
        const userMessage: Message = {
          role: 'user',
          content: messageContent,
          files: selectedFiles.length > 0 ? selectedFiles : undefined,
        };

        let updatedMessages = [...messages, userMessage];
        setMessages(updatedMessages);

        // チャットリクエストを作成
        const chatRequest: ChatRequest = {
          messages: updatedMessages,
          model: selectedModel,
        };

        // ストリーミングAPIを呼び出し
        const { reader, decoder } = await streamingApiCall(
          `${API_BASE_URL}/backend/chat`,
          {
            body: chatRequest,
            signal,
          }
        );

        // アシスタントメッセージを追加
        let assistantMessage = '';
        updatedMessages = [...updatedMessages, { role: 'assistant', content: '' }];
        setMessages(updatedMessages);

        // ストリームを読み取り
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value, { stream: true });
          assistantMessage += text;

          setMessages(prev => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              role: 'assistant',
              content: assistantMessage,
            };
            return newMessages;
          });
        }

        // 完了後にチャット履歴を保存
        const finalMessages = [
          ...updatedMessages.slice(0, -1),
          { role: 'assistant', content: assistantMessage } as Message,
        ];

        setMessages(finalMessages);

        if (currentChatId) {
          await saveChatHistory(currentChatId, finalMessages);
        }

        // 入力をクリア
        setInput('');

      } catch (error) {
        if ((error as any)?.name === 'AbortError') {
          console.log('メッセージ送信がキャンセルされました');
        } else {
          handleError(error, 'メッセージ送信');
        }
      } finally {
        abortControllerRef.current = null;
      }
    });
  }, [
    messages,
    selectedModel,
    streamingApiCall,
    API_BASE_URL,
    clearError,
    handleError,
    withLoading,
    currentChatId,
    saveChatHistory,
  ]);

  /**
   * メッセージ送信をキャンセル
   */
  const cancelMessage = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  /**
   * 編集モードを開始
   */
  const startEditMode = useCallback(() => {
    setBackupMessages([...messages]);
    setIsEditMode(true);
  }, [messages]);

  /**
   * 編集モードを終了（保存）
   */
  const saveEditMode = useCallback(async () => {
    setIsEditMode(false);
    setBackupMessages([]);

    // チャット履歴を保存
    if (currentChatId) {
      await saveChatHistory(currentChatId, messages);
    }
  }, [currentChatId, saveChatHistory, messages]);

  /**
   * 編集モードをキャンセル
   */
  const cancelEditMode = useCallback(() => {
    setMessages(backupMessages);
    setIsEditMode(false);
    setBackupMessages([]);
  }, [backupMessages]);

  /**
   * メッセージを削除
   */
  const deleteMessage = useCallback((index: number) => {
    setMessages(prev => prev.filter((_, i) => i !== index));
  }, []);

  /**
   * メッセージを編集
   */
  const editMessage = useCallback((index: number, newContent: string) => {
    setMessages(prev => prev.map((msg, i) => 
      i === index ? { ...msg, content: newContent } : msg
    ));
  }, []);

  /**
   * 全メッセージをクリア
   */
  const clearMessages = useCallback(() => {
    setMessages([]);
    setInput('');
    clearError();
  }, [clearError]);

  /**
   * メッセージを読み込み
   */
  const loadMessages = useCallback((newMessages: Message[]) => {
    setMessages(newMessages);
    clearError();
  }, [clearError]);

  /**
   * 特定のメッセージ以降を削除
   */
  const deleteMessagesFromIndex = useCallback((fromIndex: number) => {
    setMessages(prev => prev.slice(0, fromIndex));
  }, []);

  /**
   * メッセージを再生成（最後のアシスタントメッセージを削除して再送信）
   */
  const regenerateLastMessage = useCallback(async () => {
    if (messages.length < 2) return;

    // 最後のアシスタントメッセージを削除
    const messagesWithoutLast = messages.slice(0, -1);
    setMessages(messagesWithoutLast);

    // 最後のユーザーメッセージを取得
    const lastUserMessage = messagesWithoutLast[messagesWithoutLast.length - 1];
    if (lastUserMessage && lastUserMessage.role === 'user') {
      await sendMessage(lastUserMessage.content, lastUserMessage.files || []);
    }
  }, [messages, sendMessage]);

  return {
    // State
    messages,
    input,
    models,
    selectedModel,
    isProcessing,
    isEditMode,

    // Actions
    setInput,
    setSelectedModel,
    loadModels,
    sendMessage,
    cancelMessage,
    clearMessages,
    loadMessages,

    // Edit Mode
    startEditMode,
    saveEditMode,
    cancelEditMode,

    // Message Management
    deleteMessage,
    editMessage,
    deleteMessagesFromIndex,
    regenerateLastMessage,
  };
};