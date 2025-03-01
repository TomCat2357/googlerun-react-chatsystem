/**
 * frontend/src/config.ts
 *
 * このモジュールは、サーバー側設定（config）を管理します。
 * APIエンドポイントや Firebase の設定はそのままエクスポートし、
 * サーバー設定はログイン時に取得後 IndexedDB に保存し、
 * ページ読み込み時に IndexedDB から読み込むことでリロードしても設定が失われないようにします。
 */

import { openDB } from "./utils/indexedDBUtils";

// APIのエンドポイントおよびFirebase設定（.env.localに残す設定）
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL;
export const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
};

// IndexedDB の設定
const CONFIG_DB_NAME = "ServerConfigDB";
const CONFIG_DB_VERSION = 1;
const CONFIG_STORE_NAME = "config";
const CONFIG_KEY = "serverConfig";

// サーバー側設定値の初期値（ログイン時にサーバーから取得し IndexedDB に保存する）
let serverConfig = {
  MAX_IMAGES: 0,
  MAX_LONG_EDGE: 0,
  MAX_IMAGE_SIZE: 0,
  MAX_PAYLOAD_SIZE: 0,
  GOOGLE_MAPS_API_CACHE_TTL: 0,
  GEOCODING_NO_IMAGE_MAX_BATCH_SIZE: 0,
  GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE: 0,
  SPEECH_MAX_SECONDS: 0,
  MODELS: "",
  // 追加する新しい設定
  IMAGEN_MODELS: "",
  IMAGEN_NUMBER_OF_IMAGES: "",
  IMAGEN_ASPECT_RATIOS: "",
  IMAGEN_LANGUAGES: "",
  IMAGEN_ADD_WATERMARK: "",
  IMAGEN_SAFETY_FILTER_LEVELS: "",
  IMAGEN_PERSON_GENERATIONS: "",
};

/**
 * カンマ区切り文字列から選択肢とデフォルト値を抽出
 * - {}で囲まれた値をデフォルト値とする
 * - {}で囲まれた値がなければ最初の値をデフォルト値とする
 */
export function parseOptionsWithDefault(optionsStr: string): { options: string[], defaultOption: string } {
  if (!optionsStr || !optionsStr.trim()) {
    return { options: [], defaultOption: '' };
  }
  
  const items = optionsStr.split(',').map(item => item.trim());
  let defaultOption = '';
  
  // {}で囲まれた値を探してデフォルト値を設定
  const options = items.map(item => {
    if (item.startsWith('{') && item.endsWith('}')) {
      const cleanedItem = item.substring(1, item.length - 1);
      defaultOption = cleanedItem;
      return cleanedItem;
    }
    return item;
  });
  
  // デフォルト値が見つからなければ最初の値をデフォルト値とする
  if (!defaultOption && options.length > 0) {
    defaultOption = options[0];
  }
  
  return { options, defaultOption };
}

/**
 * 数値型のオプション用解析関数
 */
export function parseNumberOptionsWithDefault(optionsStr: string): { options: number[], defaultOption: number } {
  const { options: strOptions, defaultOption: strDefaultOption } = parseOptionsWithDefault(optionsStr);
  const options = strOptions.map(opt => parseInt(opt, 10)).filter(num => !isNaN(num));
  const defaultOption = parseInt(strDefaultOption, 10);
  
  return {
    options,
    defaultOption: isNaN(defaultOption) && options.length > 0 ? options[0] : defaultOption
  };
}

/**
 * サーバー設定をメモリ上と IndexedDB に保存します。
 * @param config 新しいサーバー設定
 */

export async function setServerConfig(config: typeof serverConfig) {
  serverConfig = config;
  try {
    const db = await openDB(CONFIG_DB_NAME, CONFIG_DB_VERSION, (db) => {
      if (!db.objectStoreNames.contains(CONFIG_STORE_NAME)) {
        db.createObjectStore(CONFIG_STORE_NAME, { keyPath: "id" });
      }
    });
    const tx = db.transaction(CONFIG_STORE_NAME, "readwrite");
    const store = tx.objectStore(CONFIG_STORE_NAME);
    store.put({ id: CONFIG_KEY, ...config });
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch (error) {
    console.error("IndexedDB への設定保存に失敗しました:", error);
  }
}
/**
 * 現在のメモリ上のサーバー設定を返します。
 */
export function getServerConfig() {
  return serverConfig;
}

/**
 * IndexedDB からサーバー設定を読み込み、メモリ上の設定を更新します。
 * 設定が存在しない場合は初期値をそのまま使用します。
 */
export async function loadServerConfig() {
  try {
    const db = await openDB(CONFIG_DB_NAME, CONFIG_DB_VERSION, (db) => {
      if (!db.objectStoreNames.contains(CONFIG_STORE_NAME)) {
        db.createObjectStore(CONFIG_STORE_NAME, { keyPath: "id" });
      }
    });
    return new Promise<typeof serverConfig>((resolve, reject) => {
      const tx = db.transaction(CONFIG_STORE_NAME, "readonly");
      const store = tx.objectStore(CONFIG_STORE_NAME);
      const req = store.get(CONFIG_KEY);
      req.onsuccess = () => {
        if (req.result) {
          serverConfig = req.result;
        }
        resolve(serverConfig);
      };
      req.onerror = () => {
        reject(req.error);
      };
    });
  } catch (error) {
    console.error("IndexedDB から設定の読み込みに失敗しました:", error);
    return serverConfig;
  }
}

/**
 * サーバーから設定を取得し、メモリとIndexedDBに保存する関数
 * @param token 認証トークン
 * @returns 取得したサーバー設定
 */
export async function fetchAndSaveServerConfig(token: string): Promise<typeof serverConfig> {
  try {
    const response = await fetch(`${API_BASE_URL}/backend/config`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error(`設定取得エラー: ${response.status}`);
    }

    const configData = await response.json();
    // サーバー設定をグローバルに保持するためconfig.tsにもセット
    setServerConfig(configData);

    return configData;
  } catch (error) {
    console.error("サーバー設定取得エラー:", error);
    throw error;
  }
}

// モジュール読み込み時に IndexedDB から設定をロード
loadServerConfig()
  .then((config) => {
    console.log("IndexedDB からサーバー設定をロードしました:", config);
  })
  .catch((error) => {
    console.error("サーバー設定のロード中にエラーが発生しました:", error);
  });