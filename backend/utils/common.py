# utils/common.py
import os
import json
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from fastapi import Request, HTTPException
from pydantic import BaseModel, Field
from firebase_admin import auth

# logger.pyから必要な機能をインポート
from utils.logger import logger
# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# ===== アプリケーション設定 =====
PORT = int(os.getenv("PORT", "8080"))
FRONTEND_PATH = os.getenv("FRONTEND_PATH")

# CORS設定
ORIGINS = [org for org in os.getenv("ORIGINS", "").split(",") if org]

# IPアクセス制限
ALLOWED_IPS = os.getenv("ALLOWED_IPS")

# ===== Google Cloud 設定 =====
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION")
# デプロイ時にコンソールで指定する場合もあるため、空白許容どころかいらない？
# GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# ===== Firebase設定 =====
FIREBASE_CLIENT_SECRET_PATH = os.getenv("FIREBASE_CLIENT_SECRET_PATH", "")

# ===== SSL/TLS設定 =====
# Cloud RunではSSL証明書を使用しないため、空白許容
SSL_CERT_PATH = os.getenv("SSL_CERT_PATH", "")
SSL_KEY_PATH = os.getenv("SSL_KEY_PATH", "")

# ===== API制限設定 =====
# シークレットサービスから取得する場合があるため、空白許容
GOOGLE_MAPS_API_KEY_PATH = os.getenv("GOOGLE_MAPS_API_KEY_PATH", "")
GOOGLE_MAPS_API_CACHE_TTL = int(os.getenv("GOOGLE_MAPS_API_CACHE_TTL"))
GEOCODING_NO_IMAGE_MAX_BATCH_SIZE = int(os.getenv("GEOCODING_NO_IMAGE_MAX_BATCH_SIZE"))
GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE = int(
    os.getenv("GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE")
)
# 並行処理のバッチサイズ（追加）
GEOCODING_BATCH_SIZE = int(os.getenv("GEOCODING_BATCH_SIZE", "5"))

# ===== Secret Manager設定 ===== 環境変数から取得する場合があるので空白許容
SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY = os.getenv(
    "SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY", ""
)

# ===== データ制限設定 =====
MAX_IMAGES = int(os.getenv("MAX_IMAGES"))
MAX_LONG_EDGE = int(os.getenv("MAX_LONG_EDGE"))
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE"))
MAX_AUDIO_FILES = int(os.getenv("MAX_AUDIO_FILES"))
MAX_TEXT_FILES = int(os.getenv("MAX_TEXT_FILES"))
SPEECH_MAX_SECONDS = int(os.getenv("SPEECH_MAX_SECONDS"))

# ===== モデル設定 =====
MODELS = os.getenv("MODELS")

# Imagen設定
IMAGEN_MODELS = os.getenv("IMAGEN_MODELS")
IMAGEN_NUMBER_OF_IMAGES = os.getenv("IMAGEN_NUMBER_OF_IMAGES")
IMAGEN_ASPECT_RATIOS = os.getenv("IMAGEN_ASPECT_RATIOS")
IMAGEN_LANGUAGES = os.getenv("IMAGEN_LANGUAGES")
IMAGEN_ADD_WATERMARK = os.getenv("IMAGEN_ADD_WATERMARK")
IMAGEN_SAFETY_FILTER_LEVELS = os.getenv("IMAGEN_SAFETY_FILTER_LEVELS")
IMAGEN_PERSON_GENERATIONS = os.getenv("IMAGEN_PERSON_GENERATIONS")

# 非同期ジェネレーター用ログ最大値
GEOCODING_LOG_MAX_LENGTH = int(os.getenv("GEOCODING_LOG_MAX_LENGTH"))
CHAT_LOG_MAX_LENGTH = int(os.getenv("CHAT_LOG_MAX_LENGTH"))

# 辞書ロガー用最大値
CONFIG_LOG_MAX_LENGTH = int(os.getenv("CONFIG_LOG_MAX_LENGTH"))
VERIFY_AUTH_LOG_MAX_LENGTH = int(os.getenv("VERIFY_AUTH_LOG_MAX_LENGTH"))
SPEECH2TEXT_LOG_MAX_LENGTH = int(os.getenv("SPEECH2TEXT_LOG_MAX_LENGTH"))
GENERATE_IMAGE_LOG_MAX_LENGTH = int(os.getenv("GENERATE_IMAGE_LOG_MAX_LENGTH"))
LOGOUT_LOG_MAX_LENGTH = int(os.getenv("LOGOUT_LOG_MAX_LENGTH"))
MIDDLE_WARE_LOG_MAX_LENGTH = int(os.getenv("MIDDLE_WARE_LOG_MAX_LENGTH"))

# request_idを必要としないパス。重要性が低いので未設定許容
UNNEED_REQUEST_ID_PATH = os.getenv("UNNEED_REQUEST_ID_PATH", "").split(",")
UNNEED_REQUEST_ID_PATH_STARTSWITH = os.getenv(
    "UNNEED_REQUEST_ID_PATH_STARTSWITH", ""
).split(",")
UNNEED_REQUEST_ID_PATH_ENDSWITH = os.getenv(
    "UNNEED_REQUEST_ID_PATH_ENDSWITH", ""
).split(",")

# ログでマスクするセンシティブ情報。設定しなければエラーがでる
SENSITIVE_KEYS = os.getenv("SENSITIVE_KEYS").split(",")

# Hugging Faceの認証トークン。pyannote用
HF_AUTH_TOKEN = os.getenv("HF_AUTH_TOKEN")

# GCS関連の設定
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC")
EMAIL_NOTIFICATION = bool(os.getenv("EMAIL_NOTIFICATION"))
BATCH_IMAGE_URL = os.getenv("BATCH_IMAGE_URL")

# ===== Firestore コレクション設定 =====
WHISPER_JOBS_COLLECTION = os.getenv("WHISPER_JOBS_COLLECTION")

# 環境変数DEBUGの値はlogger.pyに移動


def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からAPIキーを取得する"""
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, "")


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


# WhisperのAPI用モデルクラス
class WhisperRequest(BaseModel):
    audio_data: str
    filename: str
    description: Optional[str] = ""
    recording_date: Optional[str] = ""
    tags: Optional[List[str]] = []  # タグのリスト


class WhisperJobRequest(BaseModel):
    segments: List[Dict[str, Any]]


# 認証ミドルウェア用の依存関係
async def get_current_user(request: Request):
    """
    Extracts and verifies the current user's authentication token from the request headers.

    Validates the Authorization header, verifies the Firebase ID token, and returns the decoded token.
    Raises an HTTPException with a 401 status code if authentication fails.

    Args:
        request (Request): The incoming HTTP request containing authentication headers.

    Returns:
        dict: The decoded Firebase ID token for the authenticated user.

    Raises:
        HTTPException: If no token is present or token verification fails.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("トークンが見つかりません")
        raise HTTPException(status_code=401, detail="認証が必要です")

    token = auth_header.split("Bearer ")[1]
    try:
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        logger.info("認証成功")
        return decoded_token
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))
