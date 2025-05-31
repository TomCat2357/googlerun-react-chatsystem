from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional, ClassVar
import datetime, re


# Whisperのセグメントの型 (フロントエンドの apiTypes.ts と合わせる)
class WhisperSegment(BaseModel):
    start: float  # number は float で表現
    end: float
    text: str
    speaker: str


# モデルクラス定義
class GeocodeLineData(BaseModel):
    query: str
    has_geocode_cache: Optional[bool] = False
    has_satellite_cache: Optional[bool] = False
    has_streetview_cache: Optional[bool] = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class GeocodeRequest(BaseModel):
    mode: str
    lines: List[GeocodeLineData]
    options: Dict[str, Any]


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    model: str


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


# WhisperのuploadのAPI用モデルクラス
class WhisperUploadRequest(BaseModel):
    audio_data: str
    filename: str
    description: Optional[str] = ""
    recording_date: Optional[str] = ""
    tags: Optional[List[str]] = []  # タグのリスト
    # 話者数関連パラメータを追加
    language: str = "ja" # 言語コード。デフォルトは日本語
    initial_prompt: str = "" # Whisperの初期プロンプト。デフォルトは空文字列。
    num_speakers: Optional[int] = None  # 明示的に指定された話者数
    min_speakers: Optional[int] = 1  # 最小話者数（自動検出の範囲指定用）
    max_speakers: Optional[int] = 6  # 最大話者数（自動検出の範囲指定用）


# WhisperのFirestoreデータの型に segments を追加
class WhisperFirestoreData(BaseModel):
    job_id: str # ジョブID。リクエストIDをそのまま使用
    user_id: str # ユーザーのID。Firebase AuthのUIDを使用
    user_email: str # ユーザーのメールアドレス
    filename: str # 元の音声ファイルの名前。GCS上のファイル名ではない。
    description: str = "" # 音声ファイルの説明
    recording_date: str = "" # 録音日時。YYYY-MM-DD形式。
    gcs_bucket_name : str # GCSのバケット名
    audio_size: int  # 音声ファイルのサイズ (バイト単位)
    audio_duration_ms: int  # 音声ファイルの再生時間 (ミリ秒単位)
    file_hash: str # 音声ファイルのハッシュ値。SHA256を使用。
    language: str = "ja" # 音声ファイルの言語。デフォルトは日本語。
    initial_prompt: str = ""  # Whisperの初期プロンプト。デフォルトは空文字列。
    status: str  # "queued", "processing", "completed", "failed", "canceled"
    created_at: Any = None  # FirestoreのSERVER_TIMESTAMPを使用するため
    updated_at: Any = None  # FirestoreのSERVER_TIMESTAMPを使用するため
    process_started_at: Optional[Any] = None
    process_ended_at: Optional[Any] = None
    tags: List[str] = []

    # 以下の話者数関連フィールドを追加
    num_speakers: Optional[int] = None  # 指定された話者数
    min_speakers: Optional[int] = 1  # 最小話者数（範囲指定の場合）
    max_speakers: Optional[int] = 1  # 最大話者数（範囲指定の場合）

    error_message: Optional[str] = None

    class Config:
        # 追加のフィールドを許可しない
        extra = "forbid"

    # 例：特定のフィールドのバリデーション
    # クラス変数として有効なステータスを定義
    VALID_STATUSES: ClassVar[List[str]] = ["queued", "launched", "processing", "completed", "failed", "canceled"]
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in cls.VALID_STATUSES:
            raise ValueError(
                f"無効なステータス: {v}. 有効なステータス: {cls.VALID_STATUSES}"
            )
        return v


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
    speaker_config: Dict[str, SpeakerConfigItem]

    class Config:
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

