import { useState, useCallback } from 'react';

/**
 * ローディング状態管理フック
 * 非同期処理のローディング状態を簡単に管理
 */
export const useLoadingState = (initialState = false) => {
  const [isLoading, setIsLoading] = useState(initialState);

  /**
   * 非同期処理をローディング状態で包む
   * @param asyncFn - 実行する非同期関数
   * @returns 非同期関数の結果
   */
  const withLoading = useCallback(async <T>(
    asyncFn: () => Promise<T>
  ): Promise<T> => {
    setIsLoading(true);
    try {
      return await asyncFn();
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 複数の非同期処理を並列実行（ローディング状態付き）
   * @param asyncFns - 実行する非同期関数の配列
   * @returns 全ての非同期関数の結果の配列
   */
  const withLoadingParallel = useCallback(async <T>(
    asyncFns: (() => Promise<T>)[]
  ): Promise<T[]> => {
    setIsLoading(true);
    try {
      return await Promise.all(asyncFns.map(fn => fn()));
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 条件付きローディング状態管理
   * @param condition - ローディングを開始する条件
   * @param asyncFn - 実行する非同期関数
   * @returns 非同期関数の結果またはundefined（条件が満たされない場合）
   */
  const withConditionalLoading = useCallback(async <T>(
    condition: boolean,
    asyncFn: () => Promise<T>
  ): Promise<T | undefined> => {
    if (!condition) return undefined;
    
    return withLoading(asyncFn);
  }, [withLoading]);

  /**
   * 手動でローディング状態を設定
   */
  const setLoading = useCallback((loading: boolean) => {
    setIsLoading(loading);
  }, []);

  /**
   * ローディング状態をトグル
   */
  const toggleLoading = useCallback(() => {
    setIsLoading(prev => !prev);
  }, []);

  return {
    isLoading,
    setLoading,
    toggleLoading,
    withLoading,
    withLoadingParallel,
    withConditionalLoading,
  };
};