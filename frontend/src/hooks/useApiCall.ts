import { useCallback } from 'react';
import { useToken } from './useToken';
import { generateRequestId } from '../utils/requestIdUtils';

export interface ApiCallOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: any;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  isStreaming?: boolean;
}

export interface ApiResponse<T = any> {
  data: T;
  status: number;
  headers: Headers;
}

export interface StreamingApiResponse {
  reader: ReadableStreamDefaultReader<Uint8Array>;
  decoder: TextDecoder;
}

/**
 * 統一されたAPI呼び出しフック
 * 認証トークン、リクエストID、共通ヘッダーを自動で処理
 */
export const useApiCall = () => {
  const token = useToken();

  /**
   * 通常のAPI呼び出し（JSONレスポンス）
   */
  const apiCall = useCallback(async <T = any>(
    endpoint: string,
    options: ApiCallOptions = {}
  ): Promise<ApiResponse<T>> => {
    const {
      method = 'POST',
      body,
      headers = {},
      signal,
    } = options;

    if (!token) {
      throw new Error('認証トークンが取得できません');
    }

    const requestId = generateRequestId();
    console.log(`API呼び出しリクエストID: ${requestId}`);

    const baseHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'X-Request-Id': requestId,
      ...headers,
    };

    const response = await fetch(endpoint, {
      method,
      headers: baseHeaders,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });

    if (!response.ok) {
      let errorMessage: string;
      try {
        const errorData = await response.json();
        errorMessage = errorData.error || errorData.message || `HTTP error! status: ${response.status}`;
      } catch {
        errorMessage = `HTTP error! status: ${response.status}`;
      }
      throw new Error(errorMessage);
    }

    const data = await response.json();

    return {
      data,
      status: response.status,
      headers: response.headers,
    };
  }, [token]);

  /**
   * ストリーミングAPI呼び出し（Server-Sent Events）
   */
  const streamingApiCall = useCallback(async (
    endpoint: string,
    options: ApiCallOptions = {}
  ): Promise<StreamingApiResponse> => {
    const {
      method = 'POST',
      body,
      headers = {},
      signal,
    } = options;

    if (!token) {
      throw new Error('認証トークンが取得できません');
    }

    const requestId = generateRequestId();
    console.log(`ストリーミングAPI呼び出しリクエストID: ${requestId}`);

    const baseHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Authorization': `Bearer ${token}`,
      'X-Request-Id': requestId,
      ...headers,
    };

    const response = await fetch(endpoint, {
      method,
      headers: baseHeaders,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error('レスポンスボディが空です');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    return { reader, decoder };
  }, [token]);

  /**
   * ファイルアップロード用API呼び出し（multipart/form-data）
   */
  const uploadApiCall = useCallback(async <T = any>(
    endpoint: string,
    formData: FormData,
    options: Omit<ApiCallOptions, 'body'> = {}
  ): Promise<ApiResponse<T>> => {
    const {
      method = 'POST',
      headers = {},
      signal,
    } = options;

    if (!token) {
      throw new Error('認証トークンが取得できません');
    }

    const requestId = generateRequestId();
    console.log(`ファイルアップロードリクエストID: ${requestId}`);

    // multipart/form-dataの場合、Content-Typeは自動で設定される
    const baseHeaders: Record<string, string> = {
      'Authorization': `Bearer ${token}`,
      'X-Request-Id': requestId,
      ...headers,
    };

    const response = await fetch(endpoint, {
      method,
      headers: baseHeaders,
      body: formData,
      signal,
    });

    if (!response.ok) {
      let errorMessage: string;
      try {
        const errorData = await response.json();
        errorMessage = errorData.error || errorData.message || `HTTP error! status: ${response.status}`;
      } catch {
        errorMessage = `HTTP error! status: ${response.status}`;
      }
      throw new Error(errorMessage);
    }

    const data = await response.json();

    return {
      data,
      status: response.status,
      headers: response.headers,
    };
  }, [token]);

  return {
    apiCall,
    streamingApiCall,
    uploadApiCall,
  };
};