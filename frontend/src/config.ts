// src/config.ts

// APIのエンドポイント
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL;

// Geocoding用キャッシュTTL（秒）とミリ秒版
export const CACHE_TTL: number = Number(import.meta.env.VITE_GOOGLE_MAPS_API_CACHE_TTL) || 3600;
export const CACHE_TTL_MS: number = CACHE_TTL * 1000;

// 画像アップロード関連の定数（chatpage.tsx用）
export const MAX_IMAGES: number = Number(import.meta.env.VITE_MAX_IMAGES) || 5;
export const MAX_LONG_EDGE: number = Number(import.meta.env.VITE_MAX_LONG_EDGE) || 1568;
export const MAX_IMAGE_SIZE: number = Number(import.meta.env.VITE_MAX_IMAGE_SIZE) || 5 * 1024 * 1024;
