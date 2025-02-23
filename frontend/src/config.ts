// src/config.ts

// APIのエンドポイント
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL;

// Geocoding用キャッシュTTL（秒）とミリ秒版
export const CACHE_TTL: number = Number(import.meta.env.VITE_GOOGLE_MAPS_API_CACHE_TTL) || 3600;
export const CACHE_TTL_MS: number = CACHE_TTL * 1000;

// Gecoding用で一回の送信で得られる件数
export const NO_IMAGE_MAX_BATCH_SIZE: number = Number(import.meta.env.VITE_GEOCODING_NO_IMAGE_MAX_BATCH_SIZE);
export const WITH_IMAGE_MAX_BATCH_SIZE: number = Number(import.meta.env.VITE_GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE);

// 画像アップロード関連の定数（chatpage.tsx用）
export const MAX_IMAGES: number = Number(import.meta.env.VITE_MAX_IMAGES) || 5;
export const MAX_LONG_EDGE: number = Number(import.meta.env.VITE_MAX_LONG_EDGE) || 1568;
export const MAX_IMAGE_SIZE: number = Number(import.meta.env.VITE_MAX_IMAGE_SIZE) || 5 * 1024 * 1024;

// 音声文字起こし用チャンクサイズ（バイト単位）
// ※ 例：デフォルト500MB（524288000バイト）。この値は必ず25KB（25600バイト）の倍数になるように（足りなければ切り捨て）
export const SPEECH_CHUNK_SIZE: number = Number(import.meta.env.VITE_SPEECH_CHUNK_SIZE) || 524288000;

// 音声文字起こし用制限時間（秒） 基本３時間
export const SPEECH_MAX_SECONDS: number = Number(import.meta.env.VITE_SPEECH_MAX_SECONDS) || 10800;

