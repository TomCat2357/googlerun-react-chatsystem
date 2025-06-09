/**
 * apiUtils.ts
 * API関連の共通ユーティリティ関数
 */

import { generateRequestId } from './requestIdUtils';

export interface ApiConfig {
  baseUrl?: string;
  timeout?: number;
  retryAttempts?: number;
  retryDelay?: number;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  headers?: Record<string, string>;
  body?: any;
  signal?: AbortSignal;
  timeout?: number;
}

export interface ApiError {
  status: number;
  message: string;
  code?: string;
  details?: any;
}

/**
 * 標準のAPIヘッダーを作成
 */
export const createApiHeaders = (
  token: string,
  requestId?: string,
  customHeaders: Record<string, string> = {}
): Record<string, string> => {
  const id = requestId || generateRequestId();
  
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    'X-Request-Id': id,
    ...customHeaders,
  };
};

/**
 * multipart/form-data用のヘッダーを作成
 */
export const createFormDataHeaders = (
  token: string,
  requestId?: string,
  customHeaders: Record<string, string> = {}
): Record<string, string> => {
  const id = requestId || generateRequestId();
  
  return {
    'Authorization': `Bearer ${token}`,
    'X-Request-Id': id,
    ...customHeaders,
  };
};

/**
 * ストリーミングAPI用のヘッダーを作成
 */
export const createStreamingHeaders = (
  token: string,
  requestId?: string,
  customHeaders: Record<string, string> = {}
): Record<string, string> => {
  const id = requestId || generateRequestId();
  
  return {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
    'Authorization': `Bearer ${token}`,
    'X-Request-Id': id,
    ...customHeaders,
  };
};

/**
 * APIレスポンスの処理
 */
export const handleApiResponse = async <T = any>(response: Response): Promise<T> => {
  if (!response.ok) {
    await handleApiError(response);
  }

  // レスポンスが空の場合
  const contentLength = response.headers.get('content-length');
  if (contentLength === '0') {
    return {} as T;
  }

  const contentType = response.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    return await response.json();
  }

  return await response.text() as any;
};

/**
 * APIエラーの処理
 */
export const handleApiError = async (response: Response): Promise<never> => {
  let errorMessage: string;
  let errorCode: string | undefined;
  let errorDetails: any;

  try {
    const errorData = await response.json();
    errorMessage = errorData.error || errorData.message || `HTTP error! status: ${response.status}`;
    errorCode = errorData.code;
    errorDetails = errorData.details;
  } catch {
    errorMessage = `HTTP error! status: ${response.status}`;
  }

  const apiError: ApiError = {
    status: response.status,
    message: errorMessage,
    code: errorCode,
    details: errorDetails,
  };

  throw apiError;
};

/**
 * ストリーミングレスポンスのリーダーを作成
 */
export const createStreamReader = async (response: Response) => {
  if (!response.ok) {
    await handleApiError(response);
  }

  if (!response.body) {
    throw new Error('レスポンスボディが空です');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  return { reader, decoder };
};

/**
 * リトライ機能付きのfetch
 */
export const fetchWithRetry = async (
  url: string,
  options: RequestOptions = {},
  config: ApiConfig = {}
): Promise<Response> => {
  const {
    retryAttempts = 3,
    retryDelay = 1000,
    timeout = 30000,
  } = config;

  const { timeout: requestTimeout = timeout, ...fetchOptions } = options;

  for (let attempt = 0; attempt <= retryAttempts; attempt++) {
    try {
      // タイムアウトを設定
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), requestTimeout);

      const response = await fetch(url, {
        ...fetchOptions,
        signal: options.signal || controller.signal,
      });

      clearTimeout(timeoutId);

      // 成功またはクライアントエラー（4xx）の場合はリトライしない
      if (response.ok || (response.status >= 400 && response.status < 500)) {
        return response;
      }

      // サーバーエラー（5xx）の場合はリトライ
      if (attempt < retryAttempts) {
        console.warn(`API request failed (attempt ${attempt + 1}/${retryAttempts + 1}):`, response.status);
        await delay(retryDelay * Math.pow(2, attempt)); // Exponential backoff
        continue;
      }

      return response;
    } catch (error) {
      if (attempt < retryAttempts && !isAbortError(error)) {
        console.warn(`API request failed (attempt ${attempt + 1}/${retryAttempts + 1}):`, error);
        await delay(retryDelay * Math.pow(2, attempt));
        continue;
      }
      throw error;
    }
  }

  throw new Error('API request failed after all retry attempts');
};

/**
 * AbortErrorかどうかを判定
 */
const isAbortError = (error: any): boolean => {
  return error?.name === 'AbortError' || error?.code === 20;
};

/**
 * 指定した時間だけ待機
 */
const delay = (ms: number): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, ms));
};

/**
 * URLにクエリパラメータを追加
 */
export const addQueryParams = (
  url: string,
  params: Record<string, string | number | boolean | undefined | null>
): string => {
  const urlObj = new URL(url);
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      urlObj.searchParams.set(key, String(value));
    }
  });
  
  return urlObj.toString();
};

/**
 * FormDataを作成（ファイルアップロード用）
 */
export const createFormData = (
  data: Record<string, any>
): FormData => {
  const formData = new FormData();
  
  Object.entries(data).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      if (value instanceof File || value instanceof Blob) {
        formData.append(key, value);
      } else if (Array.isArray(value)) {
        value.forEach((item, index) => {
          if (item instanceof File || item instanceof Blob) {
            formData.append(`${key}[${index}]`, item);
          } else {
            formData.append(`${key}[${index}]`, String(item));
          }
        });
      } else if (typeof value === 'object') {
        formData.append(key, JSON.stringify(value));
      } else {
        formData.append(key, String(value));
      }
    }
  });
  
  return formData;
};

/**
 * レスポンスヘッダーから有用な情報を抽出
 */
export const extractResponseInfo = (response: Response) => {
  return {
    requestId: response.headers.get('X-Request-Id'),
    rateLimit: {
      limit: Number(response.headers.get('X-RateLimit-Limit')) || undefined,
      remaining: Number(response.headers.get('X-RateLimit-Remaining')) || undefined,
      reset: Number(response.headers.get('X-RateLimit-Reset')) || undefined,
    },
    contentType: response.headers.get('Content-Type'),
    contentLength: Number(response.headers.get('Content-Length')) || undefined,
    lastModified: response.headers.get('Last-Modified'),
    etag: response.headers.get('ETag'),
  };
};

/**
 * API接続状態をチェック
 */
export const checkApiHealth = async (
  baseUrl: string,
  timeout = 5000
): Promise<boolean> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(`${baseUrl}/health`, {
      method: 'GET',
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    return false;
  }
};

/**
 * HTTPステータスコードの説明を取得
 */
export const getStatusMessage = (status: number): string => {
  const messages: Record<number, string> = {
    200: 'OK',
    201: '作成されました',
    204: 'コンテンツなし',
    400: '不正なリクエスト',
    401: '認証が必要です',
    403: 'アクセスが禁止されています',
    404: 'リソースが見つかりません',
    409: '競合が発生しました',
    422: '処理できませんでした',
    429: 'リクエスト数が上限を超えています',
    500: 'サーバーエラーが発生しました',
    502: 'ゲートウェイエラーです',
    503: 'サービスが利用できません',
    504: 'ゲートウェイタイムアウトです',
  };

  return messages[status] || `HTTPエラー: ${status}`;
};

/**
 * APIのベースURLとパスを結合
 */
export const buildApiUrl = (baseUrl: string, path: string): string => {
  const normalizedBase = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
};