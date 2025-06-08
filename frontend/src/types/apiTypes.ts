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

// GeocodeLineDataの型定義（バックエンドと統一）
export interface GeocodeLineData {
  query: string;
  hasGeocodeCache?: boolean;
  hasSatelliteCache?: boolean;
  hasStreetviewCache?: boolean;
  latitude?: number;
  longitude?: number;
}

export interface GeocodingRequest {
  mode: string;
  lines: GeocodeLineData[];  // string[]からGeocodeLineData[]に変更
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

// WhisperのAPIリクエスト用の型（バックエンドと完全統一）
export interface WhisperUploadRequest {
  audioData?: string;  // 旧方式ではBase64データ（camelCase統一）
  gcsObject?: string;  // 新方式ではGCSオブジェクト名（camelCase統一）
  originalName?: string; // 元のファイル名（camelCase統一）
  filename?: string;    // 互換性のために残す
  description?: string;
  recordingDate?: string; // camelCase統一
  tags?: string[];
  language?: string;
  initialPrompt?: string; // camelCase統一
  numSpeakers?: number;   // camelCase統一
  minSpeakers?: number;   // camelCase統一
  maxSpeakers?: number;   // camelCase統一
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

// スピーカー設定保存用のリクエスト型（バックエンドと統一）
export interface WhisperSpeakerConfigRequest {
  speakerConfig: SpeakerConfig;  // camelCase統一済み
}

// スピーカー統計情報の型
export interface SpeakerStats {
  [speakerId: string]: {
    totalDuration: number;
    segmentCount: number;
    percentage: number;
  };
}

// Whisperジョブデータの型（バックエンドと完全統一・camelCase）
export interface WhisperJobData {
  id?: string;                   // FirestoreドキュメントのID（オプショナル）
  jobId: string;                 // camelCase統一
  userId: string;                // camelCase統一
  userEmail: string;             // camelCase統一
  filename: string;
  description?: string;
  recordingDate?: string;        // camelCase統一
  gcsBucketName: string;         // camelCase統一
  // 注意: 音声URLは動的生成される（/whisper/jobs/{file_hash}/audio_url エンドポイント）
  audioSize: number;             // camelCase統一
  audioDurationMs: number;       // camelCase統一
  fileHash: string;              // camelCase統一
  language?: string;
  initialPrompt?: string;        // camelCase統一
  status: 'queued' | 'launched' | 'processing' | 'completed' | 'failed' | 'canceled';
  createdAt: any;                // camelCase統一
  updatedAt: any;                // camelCase統一
  processStartedAt?: any;        // camelCase統一
  processEndedAt?: any;          // camelCase統一
  tags?: string[];
  numSpeakers?: number;          // camelCase統一
  minSpeakers?: number;          // camelCase統一
  maxSpeakers?: number;          // camelCase統一
  errorMessage?: string;         // camelCase統一
  segments?: WhisperSegment[];   // 詳細表示時のみ含まれる
}