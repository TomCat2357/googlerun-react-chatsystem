from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional

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


# Whisperでのfirebase保存データの型
class WhisperFirestoreFirestoreData(BaseModel):
    job_id: str
    user_id: str
    user_email: str
    filename: str
    description: str = ""
    recording_date: str = ""
    gcs_audio_path: str
    file_hash: str
    status: str  # "queued", "processing", "completed", "failed", "canceled"
    created_at: Any = None  # FirestoreのSERVER_TIMESTAMPを使用するため
    updated_at: Any = None  # FirestoreのSERVER_TIMESTAMPを使用するため
    process_started_at: Optional[Any] = None
    process_ended_at: Optional[Any] = None
    tags: List[str] = []
    error_message: Optional[str] = None
    timestamp: Optional[str] = None  # 追加したtimestampフィールド
    
    class Config:
        # 追加のフィールドを許可しない
        extra = "forbid"
    # 例：特定のフィールドのバリデーション
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        valid_statuses = ["queued", "processing", "completed", "failed", "canceled"]
        if v not in valid_statuses:
            raise ValueError(f"無効なステータス: {v}. 有効なステータス: {valid_statuses}")
        return v

# whisper関係のpub/subメッセージの型
class WhisperPubSubMessageData(BaseModel):
    job_id: str
    user_id: str
    user_email: str
    file_hash: str
    event_type: str
    status: str
    timestamp: str
    
    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, v):
        valid_event_types = ["new_job", "progress_update", "job_completed", "job_failed", "job_canceled"]
        if v not in valid_event_types:
            raise ValueError(f"無効なイベントタイプ: {v}. 有効なイベントタイプ: {valid_event_types}")
        return v
        
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        valid_statuses = ["queued", "processing", "completed", "failed", "canceled"]
        if v not in valid_statuses:
            raise ValueError(f"無効なステータス: {v}. 有効なステータス: {valid_statuses}")
        return v