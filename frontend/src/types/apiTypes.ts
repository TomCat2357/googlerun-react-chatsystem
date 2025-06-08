// apiTypes.ts
import { FileData } from "../utils/fileUtils";

// FileDataを再エクスポート
export type { FileData };

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
  id?: number;
  title: string;
  model?: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
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
  audio_data?: string;  // 旧方式ではBase64データ
  gcs_object?: string;  // 新方式ではGCSオブジェクト名
  original_name?: string; // 元のファイル名
  filename?: string;    // 互換性のために残す
  description?: string;
  recording_date?: string;
  tags?: string[];
  language?: string;
  initial_prompt?: string;
  num_speakers?: number;
  min_speakers?: number;
  max_speakers?: number;
}

// Whisperのセグメント型
export interface WhisperSegment {
  start: number;
  end: number;
  text: string;
  speaker: string;
}

// スピーカー設定の型
export interface SpeakerConfig {
  [speakerId: string]: {
    name: string;
    color: string;
  };
}

// スピーカー設定保存用のリクエスト型
export interface WhisperSpeakerConfigRequest {
  speakerConfig: SpeakerConfig;
}

// スピーカー統計情報の型
export interface SpeakerStats {
  [speakerId: string]: {
    totalDuration: number;
    segmentCount: number;
    percentage: number;
  };
}