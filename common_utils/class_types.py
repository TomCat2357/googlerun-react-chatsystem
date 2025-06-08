from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional, ClassVar
import datetime, re


# Whisperのセグメントの型 (フロントエンドの apiTypes.ts と合わせる)
class WhisperSegment(BaseModel):
    start: float  # number は float で表現
    end: float
    text: str
    speaker: str


# モデルクラス定義（GeocodeLineDataは下で再定義）


class GeocodeLineData(BaseModel):
    query: str
    hasGeocodeCache: Optional[bool] = Field(default=False, alias="has_geocode_cache")
    hasSatelliteCache: Optional[bool] = Field(default=False, alias="has_satellite_cache")
    hasStreetviewCache: Optional[bool] = Field(default=False, alias="has_streetview_cache")
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        populate_by_name = True  # camelCaseとsnake_case両方を受け入れ
        extra = "forbid"


class GeocodingRequest(BaseModel):  # 名前をフロントエンドに合わせる
    mode: str
    lines: List[GeocodeLineData]
    options: Dict[str, Any]


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    model: str
    chunked: Optional[bool] = None
    chunkId: Optional[str] = Field(default=None, alias="chunk_id")
    chunkIndex: Optional[int] = Field(default=None, alias="chunk_index")
    totalChunks: Optional[int] = Field(default=None, alias="total_chunks")
    chunkData: Optional[str] = Field(default=None, alias="chunk_data")

    class Config:
        populate_by_name = True  # camelCaseとsnake_case両方を受け入れ
        extra = "forbid"


class SpeechToTextRequest(BaseModel):
    audio_data: str


class GenerateImageRequest(BaseModel):
    prompt: str
    model_name: str
    negative_prompt: Optional[str] = None
    number_of_images: Optional[int] = None
    seed: Optional[int] = None
    aspect_ratio: Optional[str] = None
    language: Optional[str] = "auto"
    add_watermark: Optional[bool] = None
    safety_filter_level: Optional[str] = None
    person_generation: Optional[str] = None


# WhisperのuploadのAPI用モデルクラス（フロントエンドに合わせる）
class WhisperUploadRequest(BaseModel):
    audioData: Optional[str] = Field(default=None, alias="audio_data")  # 旧方式ではBase64データ
    gcsObject: Optional[str] = Field(default=None, alias="gcs_object")  # 新方式ではGCSオブジェクト名
    originalName: Optional[str] = Field(default=None, alias="original_name") # 元のファイル名
    filename: Optional[str] = None    # 互換性のために残す
    description: Optional[str] = ""
    recordingDate: Optional[str] = Field(default="", alias="recording_date")
    tags: Optional[List[str]] = []  # タグのリスト
    # 話者数関連パラメータを追加
    language: Optional[str] = "ja" # 言語コード。デフォルトは日本語
    initialPrompt: str = Field(default="", alias="initial_prompt") # Whisperの初期プロンプト。デフォルトは空文字列。
    numSpeakers: Optional[int] = Field(default=None, alias="num_speakers")  # 明示的に指定された話者数
    minSpeakers: Optional[int] = Field(default=1, alias="min_speakers")  # 最小話者数（自動検出の範囲指定用）
    maxSpeakers: Optional[int] = Field(default=6, alias="max_speakers")  # 最大話者数（自動検出の範囲指定用）

    class Config:
        populate_by_name = True  # camelCaseとsnake_case両方を受け入れ
        extra = "forbid"


# WhisperのFirestoreデータの型に segments を追加（フロントエンドのWhisperJobDataと統一）
class WhisperJobData(BaseModel):  # 名前をフロントエンドに合わせる
    id: Optional[str] = None  # FirestoreドキュメントのID
    jobId: str = Field(alias="job_id")  # ジョブID。リクエストIDをそのまま使用
    userId: str = Field(alias="user_id")  # ユーザーのID。Firebase AuthのUIDを使用
    userEmail: str = Field(alias="user_email")  # ユーザーのメールアドレス
    filename: str # 元の音声ファイルの名前。GCS上のファイル名ではない。
    description: Optional[str] = "" # 音声ファイルの説明
    recordingDate: Optional[str] = Field(default="", alias="recording_date") # 録音日時。YYYY-MM-DD形式。
    gcsBucketName: str = Field(alias="gcs_bucket_name") # GCSのバケット名
    # 注意: 音声ファイルのGCSパスは WHISPER_AUDIO_BLOB テンプレート（{file_hash}/audio.wav）で決定される
    audioSize: int = Field(alias="audio_size")  # 音声ファイルのサイズ (バイト単位)
    audioDurationMs: int = Field(alias="audio_duration_ms")  # 音声ファイルの再生時間 (ミリ秒単位)
    fileHash: str = Field(alias="file_hash") # 音声ファイルのハッシュ値。SHA256を使用。
    language: Optional[str] = "ja" # 音声ファイルの言語。デフォルトは日本語。
    initialPrompt: str = Field(default="", alias="initial_prompt")  # Whisperの初期プロンプト。デフォルトは空文字列。
    status: str  # "queued", "launched", "processing", "completed", "failed", "canceled"
    createdAt: Any = Field(default=None, alias="created_at")  # FirestoreのSERVER_TIMESTAMPを使用するため
    updatedAt: Any = Field(default=None, alias="updated_at")  # FirestoreのSERVER_TIMESTAMPを使用するため
    processStartedAt: Optional[Any] = Field(default=None, alias="process_started_at")
    processEndedAt: Optional[Any] = Field(default=None, alias="process_ended_at")
    tags: Optional[List[str]] = []

    # 以下の話者数関連フィールドを追加
    numSpeakers: Optional[int] = Field(default=None, alias="num_speakers")  # 指定された話者数
    minSpeakers: Optional[int] = Field(default=1, alias="min_speakers")  # 最小話者数（範囲指定の場合）
    maxSpeakers: Optional[int] = Field(default=1, alias="max_speakers")  # 最大話者数（範囲指定の場合）

    errorMessage: Optional[str] = Field(default=None, alias="error_message")
    segments: Optional[List[WhisperSegment]] = None  # 詳細表示時のみ含まれる

    class Config:
        populate_by_name = True  # camelCaseとsnake_case両方を受け入れ
        extra = "forbid"


# 下位互換性のためのエイリアス
WhisperFirestoreData = WhisperJobData


# Whisper編集リクエストの型
class WhisperEditRequest(BaseModel):
    segments: List[WhisperSegment]

# スピーカー設定の型
class SpeakerConfigItem(BaseModel):
    name: str
    color: str

    class Config:
        extra = "forbid"

class WhisperSpeakerConfigRequest(BaseModel):
    speakerConfig: Dict[str, SpeakerConfigItem] = Field(alias="speaker_config")

    class Config:
        populate_by_name = True  # camelCaseとsnake_case両方を受け入れ
        extra = "forbid"

# whisper関係のpub/subメッセージの型
# whisper関係のpub/subメッセージの型 (GCP Batchからの通知を想定)
class WhisperPubSubMessageData(BaseModel):
    job_id: str
    event_type: str # e.g., "job_completed", "job_failed" (consistent with whisper_batch/app/main.py)
    error_message: Optional[str] = None
    timestamp: str # ISO 8601 format

    class Config:
        # 追加のフィールドを許可しない
        extra = "forbid"

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v):
        # Adjusted to include common batch outcomes.
        valid_event_types = ["new_job", "job_completed", "job_failed", "job_canceled", "batch_complete", "batch_failed"]
        if v not in valid_event_types:
            raise ValueError(
                f"無効なイベントタイプ: {v}. 有効なイベントタイプ: {valid_event_types}"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v):
        # ISO 8601形式のバリデーション
        iso8601_pattern = r"^(-?(?:[1-9][0-9]*)?[0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])T(2[0-3]|[01][0-9]):([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?(Z|[+-](?:2[0-3]|[01][0-9]):[0-5][0-9])?$"
        if not re.match(iso8601_pattern, v):
            try:
                # 文字列をパースしてみて、パースできればOK
                datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"timestampはISO 8601形式である必要があります: {v}")
        return v

# Parameter for GCP Batch job environment variables (from whisper_queue/app/main.py)
# This defines what the container (whisper_batch/app/main.py) expects as env vars.
class WhisperBatchParameter(BaseModel):
    JOB_ID: str
    FULL_AUDIO_PATH: str             # Full GCS path gs://bucket/path/to/audio.mp3
    FULL_TRANSCRIPTION_PATH: str     # Full GCS path gs://bucket/path/to/output.json
    HF_AUTH_TOKEN: str
    NUM_SPEAKERS: Optional[str] = "" # Needs to be string for environment variable
    MIN_SPEAKERS: str = "1"
    MAX_SPEAKERS: str = "1"
    LANGUAGE: str = "ja"
    INITIAL_PROMPT: str = ""

    class Config:
        extra = "forbid"

