// apiTypes.ts
import { FileData } from "../utils/fileUtils";

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  images?: string[]; // 従来の画像添付（base64文字列の配列）
  files?: FileData[]; // 新しいファイル管理形式
  audioFiles?: Array<{ name: string; content: string }>; // 音声ファイル
  textFiles?: Array<{ name: string; type: string; content: string }>; // テキストファイル
}

export interface ChatRequest {
  messages: Message[];
  model: string;
  chunked?: boolean;
  chunkId?: string;
  chunkIndex?: number;
  totalChunks?: number;
  chunkData?: string;
}

export interface ChatHistory {
  id: number;
  title: string;
  messages: Message[];
  lastPromptDate: string;
}

export interface GeocodingRequest {
  mode: string;
  lines: string[];
  options: Record<string, any>;
}

export interface Config {
  MAX_IMAGES: number;
  MAX_LONG_EDGE: number;
  MAX_IMAGE_SIZE: number;
  MAX_PAYLOAD_SIZE: number;
  MODELS: string;
  [key: string]: any;
}