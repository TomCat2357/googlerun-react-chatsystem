import { useState, useCallback, useEffect } from 'react';
import { ChatHistory, Message } from '../types/apiTypes';
import { useErrorHandler } from './useErrorHandler';

/**
 * チャット履歴管理フック
 * LocalStorageを使用したチャット履歴の保存・読み込み・管理
 */
export const useChatHistory = () => {
  const [chatHistories, setChatHistories] = useState<ChatHistory[]>([]);
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const { handleError, clearError } = useErrorHandler();

  /**
   * LocalStorageから履歴を取得するヘルパー関数
   */
  const getStoredHistories = useCallback((): ChatHistory[] => {
    try {
      const stored = localStorage.getItem('chatHistories');
      const histories = stored ? JSON.parse(stored) : [];
      return histories.map((h: any) => ({
        ...h,
        createdAt: new Date(h.createdAt),
        updatedAt: new Date(h.updatedAt),
      }));
    } catch {
      return [];
    }
  }, []);

  /**
   * LocalStorageに履歴を保存するヘルパー関数
   */
  const saveHistoriesToStorage = useCallback((histories: ChatHistory[]) => {
    localStorage.setItem('chatHistories', JSON.stringify(histories));
  }, []);

  /**
   * 全てのチャット履歴を読み込み
   */
  const loadChatHistories = useCallback(async () => {
    setIsLoading(true);
    clearError();

    try {
      const histories = getStoredHistories();
      setChatHistories(histories);
    } catch (error) {
      handleError(error, 'チャット履歴読み込み');
    } finally {
      setIsLoading(false);
    }
  }, [handleError, clearError, getStoredHistories]);

  /**
   * 新しいチャットを作成
   */
  const createNewChat = useCallback(async (
    title: string = '新しいチャット',
    model: string = ''
  ): Promise<number> => {
    try {
      const newChatId = Date.now();
      const newHistory: ChatHistory = {
        id: newChatId,
        title,
        model,
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      const histories = getStoredHistories();
      histories.push(newHistory);
      saveHistoriesToStorage(histories);
      
      await loadChatHistories();
      setCurrentChatId(newChatId);
      return newChatId;
    } catch (error) {
      handleError(error, '新しいチャット作成');
      throw error;
    }
  }, [handleError, loadChatHistories, getStoredHistories, saveHistoriesToStorage]);

  /**
   * チャット履歴を保存/更新
   */
  const saveChatHistory = useCallback(async (
    chatId: number,
    messages: Message[],
    title?: string,
    model?: string
  ) => {
    try {
      const histories = getStoredHistories();
      const existingIndex = histories.findIndex(h => h.id === chatId);
      
      if (existingIndex === -1) {
        throw new Error('チャット履歴が見つかりません');
      }

      const updatedHistory: ChatHistory = {
        ...histories[existingIndex],
        messages,
        title: title || histories[existingIndex].title,
        model: model || histories[existingIndex].model,
        updatedAt: new Date(),
      };

      histories[existingIndex] = updatedHistory;
      saveHistoriesToStorage(histories);
      
      setChatHistories(histories);
    } catch (error) {
      handleError(error, 'チャット履歴保存');
    }
  }, [handleError, getStoredHistories, saveHistoriesToStorage]);

  /**
   * チャット履歴を削除
   */
  const deleteChatHistory = useCallback(async (chatId: number) => {
    try {
      const histories = getStoredHistories();
      const filteredHistories = histories.filter(h => h.id !== chatId);
      saveHistoriesToStorage(filteredHistories);
      
      setChatHistories(filteredHistories);
      
      if (currentChatId === chatId) {
        setCurrentChatId(null);
      }
    } catch (error) {
      handleError(error, 'チャット履歴削除');
    }
  }, [currentChatId, handleError, getStoredHistories, saveHistoriesToStorage]);

  /**
   * チャット履歴をロード
   */
  const loadChatHistory = useCallback(async (chatId: number): Promise<Message[]> => {
    try {
      const histories = getStoredHistories();
      const history = histories.find(h => h.id === chatId);
      setCurrentChatId(chatId);
      return history ? history.messages : [];
    } catch (error) {
      handleError(error, 'チャット履歴ロード');
      return [];
    }
  }, [handleError, getStoredHistories]);

  /**
   * チャットタイトルを更新
   */
  const updateChatTitle = useCallback(async (chatId: number, newTitle: string) => {
    try {
      const histories = getStoredHistories();
      const existingIndex = histories.findIndex(h => h.id === chatId);
      
      if (existingIndex === -1) {
        throw new Error('チャット履歴が見つかりません');
      }

      const updatedHistory: ChatHistory = {
        ...histories[existingIndex],
        title: newTitle,
        updatedAt: new Date(),
      };

      histories[existingIndex] = updatedHistory;
      saveHistoriesToStorage(histories);
      setChatHistories(histories);
    } catch (error) {
      handleError(error, 'チャットタイトル更新');
    }
  }, [handleError, getStoredHistories, saveHistoriesToStorage]);

  /**
   * 全てのチャット履歴を削除
   */
  const clearAllChatHistories = useCallback(async () => {
    try {
      localStorage.removeItem('chatHistories');
      setChatHistories([]);
      setCurrentChatId(null);
    } catch (error) {
      handleError(error, '全チャット履歴削除');
    }
  }, [handleError]);

  /**
   * 現在のチャット履歴を取得
   */
  const getCurrentChatHistory = useCallback((): ChatHistory | null => {
    if (!currentChatId) return null;
    return chatHistories.find(h => h.id === currentChatId) || null;
  }, [currentChatId, chatHistories]);

  /**
   * チャット履歴をエクスポート
   */
  const exportChatHistory = useCallback(async (chatId: number): Promise<string> => {
    try {
      const histories = getStoredHistories();
      const history = histories.find(h => h.id === chatId);
      if (!history) {
        throw new Error('チャット履歴が見つかりません');
      }

      return JSON.stringify(history, null, 2);
    } catch (error) {
      handleError(error, 'チャット履歴エクスポート');
      throw error;
    }
  }, [handleError, getStoredHistories]);

  /**
   * チャット履歴をインポート
   */
  const importChatHistory = useCallback(async (historyJson: string): Promise<number> => {
    try {
      const history = JSON.parse(historyJson) as ChatHistory;
      
      // 新しいIDを割り当て
      const newChatId = Date.now();
      const newHistory: ChatHistory = {
        ...history,
        id: newChatId,
        createdAt: new Date(history.createdAt),
        updatedAt: new Date(),
      };
      
      const histories = getStoredHistories();
      histories.push(newHistory);
      saveHistoriesToStorage(histories);
      
      await loadChatHistories();
      return newChatId;
    } catch (error) {
      handleError(error, 'チャット履歴インポート');
      throw error;
    }
  }, [handleError, loadChatHistories, getStoredHistories, saveHistoriesToStorage]);

  /**
   * 初期化時にチャット履歴を読み込み
   */
  useEffect(() => {
    loadChatHistories();
  }, [loadChatHistories]);

  return {
    // State
    chatHistories,
    currentChatId,
    isLoading,

    // Actions
    setCurrentChatId,
    createNewChat,
    saveChatHistory,
    deleteChatHistory,
    loadChatHistory,
    loadChatHistories,
    updateChatTitle,
    clearAllChatHistories,

    // Utils
    getCurrentChatHistory,
    exportChatHistory,
    importChatHistory,
  };
};