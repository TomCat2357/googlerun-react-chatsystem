// src/config.ts

// APIのエンドポイントおよびFirebase設定（.env.localに残す設定）
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL;
export const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
};

// サーバー側設定値（ログイン時にサーバーから取得し、IndexedDB等に保存する）
let serverConfig = {
  MAX_IMAGES: 0,
  MAX_LONG_EDGE: 0,
  MAX_IMAGE_SIZE: 0,
  GOOGLE_MAPS_API_CACHE_TTL: 0,
  GEOCODING_NO_IMAGE_MAX_BATCH_SIZE: 0,
  GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE: 0,
  SPEECH_CHUNK_SIZE: 0,
  SPEECH_MAX_SECONDS: 0,
  MODELS: ""
};

export function setServerConfig(config: typeof serverConfig) {
  serverConfig = config;
}

export function getServerConfig() {
  return serverConfig;
}
