# utils/common.py
import logging
import os
import base64
import io
import ipaddress
from PIL import Image
from google.cloud import secretmanager
from firebase_admin import auth, credentials
from typing import Dict, Optional, Any, List
from fastapi import HTTPException, Request
import time
import json
from functools import wraps
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = './config_develop/.env.develop'
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

# グローバルなチャンク保存用辞書
CHUNK_STORE = {}

# ===== アプリケーション設定 =====
PORT = int(os.getenv("PORT", '8000'))
FRONTEND_PATH = os.getenv("FRONTEND_PATH")
DEBUG = bool(int(os.getenv("DEBUG", "0")))


# CORS設定
ORIGINS = [org for org in os.getenv("ORIGINS").split(",") if org]

# IPアクセス制限
ALLOWED_IPS = os.getenv("ALLOWED_IPS")

# ===== Google Cloud 設定 =====
VERTEX_PROJECT = os.getenv("VERTEX_PROJECT")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION")
# デプロイ時にコンソールで指定する場合もあるため、空白許容どころかいらない？
# GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# ===== Firebase設定 =====
FIREBASE_CLIENT_SECRET_PATH = os.getenv("FIREBASE_CLIENT_SECRET_PATH")

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
# ===== Secret Manager設定 ===== 環境変数から取得する場合があるので空白許容
SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY = os.getenv("SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY", "")

# ===== データ制限設定 =====
MAX_PAYLOAD_SIZE = int(os.getenv("MAX_PAYLOAD_SIZE"))
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


# Secret Managerからシークレットを取得するための関数
def access_secret(secret_id, version_id="latest"):
    """
    Secret Managerからシークレットを取得する関数
    グーグルに問い合わせるときのnameは以下の構造になっている。
    projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}
    シークレットマネージャーで作成した場合は、
    projects/{PROJECT_ID}/secrets/{secret_id}
    が得られるが、PROJECT_IDは数値であるが、文字列の方のIDでもOK
    versions情報も下記コードのとおりで支障ない。
    """
    try:
        logger.info(f"Secret Managerから{secret_id}を取得しています")
        
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{VERTEX_PROJECT}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(
            f"Secret Managerからのシークレット取得に失敗: {str(e)}", exc_info=True
        )
        return None


# Google Maps APIキーを取得するための関数
def get_google_maps_api_key():
    """
    環境変数からGoogle Maps APIキーを取得し、なければSecret Managerから取得する
    """

    if GOOGLE_MAPS_API_KEY_PATH and os.path.exists(GOOGLE_MAPS_API_KEY_PATH):
        with open(GOOGLE_MAPS_API_KEY_PATH, "rt") as f:
            logger.info(
                "環境変数にGoogle Maps APIキーが設定されているため、ファイルから取得します"
            )
            api_key = f.read()
    else:
        logger.info(
            "環境変数にGoogle Maps APIキーが設定されていないため、Secret Managerから取得します"
        )
        api_key = access_secret(SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY)
        if not api_key:
            raise Exception("Google Maps APIキーが見つかりません")
    return api_key


def process_uploaded_image(image_data: str) -> str:
    """
    画像データを処理し、サイズや形式を調整する
    """
    try:
        header = None
        if image_data.startswith("data:"):
            header, image_data = image_data.split(",", 1)
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        width, height = image.size
        logger.info(
            "元の画像サイズ: %dx%dpx, 容量: %.1fKB",
            width,
            height,
            len(image_bytes) / 1024,
        )
        if max(width, height) > MAX_LONG_EDGE:
            scale = MAX_LONG_EDGE / max(width, height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info("リサイズ後: %dx%dpx", new_width, new_height)
        quality = 85
        output = io.BytesIO()
        output_format = "JPEG"
        mime_type = "image/jpeg"
        if header and "png" in header.lower():
            output_format = "PNG"
            mime_type = "image/png"
            image.save(output, format=output_format, optimize=True)
        else:
            image = image.convert("RGB")
            image.save(output, format=output_format, quality=quality, optimize=True)
        output_data = output.getvalue()
        logger.info(
            "圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
        )
        while len(output_data) > MAX_IMAGE_SIZE and quality > 30:
            quality -= 10
            output = io.BytesIO()
            image.save(output, format=output_format, quality=quality, optimize=True)
            output_data = output.getvalue()
            logger.info(
                "再圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
            )
        processed_base64 = base64.b64encode(output_data).decode("utf-8")
        return f"data:{mime_type};base64,{processed_base64}"
    except Exception as e:
        logger.error("画像処理エラー: %s", str(e), exc_info=True)
        return image_data


def verify_firebase_token(token: str) -> Dict[str, Any]:
    """Firebase認証トークンを検証し、デコードされたトークンを返す"""
    try:
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        return decoded_token
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        raise e


def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からAPIキーを取得する"""
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, "")


def limit_remote_addr(request: Request):
    """リクエスト送信元IPが許可リストに含まれていなければ403を返す"""
    remote_addr = request.headers.get("X-Forwarded-For", None)
    if not remote_addr:
        client_host = request.client.host if request.client else None
        remote_addr = client_host

    logger.info(f"X-Forwarded-For: {remote_addr}")
    if remote_addr and "," in remote_addr:
        remote_addr = remote_addr.split(",")[0].strip()
    try:
        client_ip = ipaddress.ip_address(remote_addr)
        logger.info(f"@リクエスト送信元IP: {client_ip}")
    except ValueError:
        time.sleep(0.05)
        raise HTTPException(status_code=400, detail="不正なIPアドレス形式です")

    # ALLOWED_IPSは.envから取得する設定とする
    allowed_tokens = ALLOWED_IPS
    logger.info(f'許可されたIPアドレスまたはネットワーク: {allowed_tokens}')
    allowed_networks = []
    for token in allowed_tokens.split(","):
        token = token.strip()
        if token:
            logger.info(f'許可されたIPアドレスまたはネットワーク: {token}')
            try:
                if "/" in token:
                    network = ipaddress.ip_network(token, strict=False)
                else:
                    ip = ipaddress.ip_address(token)
                    network = ipaddress.ip_network(
                        f"{ip}/{'32' if ip.version == 4 else '128'}"
                    )
                allowed_networks.append(network)
            except ValueError as e:
                logger.error(
                    f"無効なIPアドレスまたはネットワーク形式: {token}, エラー: {e}"
                )

    # IPがいずれかの許可されたネットワークに含まれているかチェック
    for network in allowed_networks:
        if client_ip in network:
            return  # 許可されている場合、処理継続

    time.sleep(0.05)
    raise HTTPException(status_code=403, detail="アクセスが許可されていません")
