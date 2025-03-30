// apiTypes.ts
import { FileData } from "../utils/fileUtils";

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  files?: FileData[]; // 統一されたファイル管理形式
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
  MAX_AUDIO_FILES: number;
  MAX_TEXT_FILES: number;
  MAX_LONG_EDGE: number;
  MAX_IMAGE_SIZE: number;
  MAX_PAYLOAD_SIZE: number;
  MODELS: string;
  [key: string]: any;
}

// WhisperのAPIリクエスト用の型
export interface WhisperUploadRequest {
  audio_data: string;
  filename: string;
  description?: string;
  recording_date?: string;
  tags?: string[];
}

// Whisperのセグメント型
export interface WhisperSegment {
  start: number;
  end: number;
  text: string;
  speaker: string;
}