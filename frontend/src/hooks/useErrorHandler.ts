import { useState, useCallback } from 'react';

export interface ErrorInfo {
  message: string;
  timestamp: Date;
  context?: string;
}

/**
 * 統一されたエラーハンドリングフック
 * エラー状態の管理と処理を簡素化
 */
export const useErrorHandler = () => {
  const [error, setError] = useState<string | null>(null);
  const [errorInfo, setErrorInfo] = useState<ErrorInfo | null>(null);

  /**
   * エラーを処理して状態を更新
   * @param error - エラーオブジェクト（Error、string、unknownなど）
   * @param context - エラーが発生したコンテキスト（オプション）
   */
  const handleError = useCallback((error: unknown, context?: string) => {
    let errorMessage: string;

    if (error instanceof Error) {
      errorMessage = error.message;
    } else if (typeof error === 'string') {
      errorMessage = error;
    } else if (error && typeof error === 'object' && 'message' in error) {
      errorMessage = String((error as any).message);
    } else {
      errorMessage = '予期しないエラーが発生しました';
    }

    console.error('エラーが発生しました:', error, context ? `コンテキスト: ${context}` : '');

    const info: ErrorInfo = {
      message: errorMessage,
      timestamp: new Date(),
      context,
    };

    setError(errorMessage);
    setErrorInfo(info);
  }, []);

  /**
   * エラー状態をクリア
   */
  const clearError = useCallback(() => {
    setError(null);
    setErrorInfo(null);
  }, []);

  /**
   * API エラーを処理（レスポンスから詳細なエラー情報を抽出）
   * @param response - Fetch API レスポンス
   * @param context - エラーが発生したコンテキスト
   */
  const handleApiError = useCallback(async (response: Response, context?: string) => {
    let errorMessage: string;

    try {
      const errorData = await response.json();
      errorMessage = errorData.error || errorData.message || `HTTP error! status: ${response.status}`;
    } catch {
      errorMessage = `HTTP error! status: ${response.status}`;
    }

    handleError(new Error(errorMessage), context);
  }, [handleError]);

  /**
   * 非同期処理を安全に実行（エラーハンドリング付き）
   * @param asyncFn - 実行する非同期関数
   * @param context - エラーが発生した際のコンテキスト
   * @returns 非同期関数の結果またはundefined（エラー時）
   */
  const withErrorHandling = useCallback(async <T>(
    asyncFn: () => Promise<T>,
    context?: string
  ): Promise<T | undefined> => {
    try {
      return await asyncFn();
    } catch (err) {
      handleError(err, context);
      return undefined;
    }
  }, [handleError]);

  /**
   * フォームバリデーションエラーを処理
   * @param fieldName - フィールド名
   * @param value - 値
   * @param validation - バリデーション関数
   * @returns バリデーション結果（true: 正常、false: エラー）
   */
  const validateField = useCallback((
    fieldName: string,
    value: any,
    validation: (value: any) => string | null
  ): boolean => {
    const errorMessage = validation(value);
    
    if (errorMessage) {
      handleError(new Error(errorMessage), `フォームバリデーション: ${fieldName}`);
      return false;
    }
    
    return true;
  }, [handleError]);

  /**
   * 複数のバリデーションを同時実行
   * @param validations - フィールド名と値、バリデーション関数のペア
   * @returns 全てのバリデーションが成功したかどうか
   */
  const validateFields = useCallback((
    validations: Array<{
      fieldName: string;
      value: any;
      validation: (value: any) => string | null;
    }>
  ): boolean => {
    const errors: string[] = [];

    for (const { fieldName, value, validation } of validations) {
      const errorMessage = validation(value);
      if (errorMessage) {
        errors.push(`${fieldName}: ${errorMessage}`);
      }
    }

    if (errors.length > 0) {
      handleError(new Error(errors.join(', ')), 'フォームバリデーション');
      return false;
    }

    return true;
  }, [handleError]);

  return {
    error,
    errorInfo,
    hasError: error !== null,
    handleError,
    clearError,
    handleApiError,
    withErrorHandling,
    validateField,
    validateFields,
  };
};