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
from copy import copy
from functools import wraps

# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 環境変数DEBUGの値を取得し、デバッグモードの設定を行う
# デフォルトは空文字列
debug = os.getenv("DEBUG", "")
# DEBUGが未設定、"false"、"0"の場合はデバッグモードをオフに
if not debug or debug.lower() == "false" or debug == "0":
    DEBUG = False
else:
    DEBUG = True

# ロギング設定の初期化
if DEBUG:
    # デバッグモード時のログ設定
    # - ログレベル: DEBUG（詳細なログを出力）
    # - フォーマット: タイムスタンプ、ログレベル、ファイル名、行番号、メッセージ
    # - 出力先: コンソール(StreamHandler)とファイル(app_debug.log)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("app_debug.log")],
    )
else:
    # 本番モード時のログ設定
    # - ログレベル: INFO（重要な情報のみ出力）
    # - フォーマット: タイムスタンプ、ログレベル、メッセージ（ファイル情報なし）
    # - 出力先: コンソール(StreamHandler)とファイル(app.log)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
    )
# 現在のモジュール用のロガーを取得
logger = logging.getLogger(__name__)

def wrap_asyncgenerator_logger(meta_info : dict = {}):
    """
    非同期ジェネレーター関数をラップしてログ出力を追加するデコレータ関数
    
    Args:
        meta_info: ログに追加する追加情報の辞書
        
    Returns:
        decorator: ラップする非同期ジェネレーター関数を受け取るデコレータ関数
    """
    def decorator(generator_func):
        @wraps(generator_func)
        async def wrapper(*args, **kwargs):
            # meta_infoパラメータをクロージャから取得または、kwargsから取得
            local_meta_info = meta_info or kwargs.get("meta_info")
            
            # 元のジェネレーター関数を実行し、各チャンクを処理
            async for chunk in generator_func(*args, **kwargs):
                # ログ用の辞書を準備（meta_infoのディープコピーまたは新規辞書）
                if isinstance(local_meta_info, dict):
                    streaming_log = copy(local_meta_info)
                else:
                    streaming_log = {}
                    
                # 現在のチャンクをログ辞書に追加してログ出力
                streaming_log["chunk"] = chunk
                logger.info(streaming_log)
                
                # チャンクを次の処理へ渡す
                yield chunk
        return wrapper
    return decorator

# ===== アプリケーション設定 =====
PORT = int(os.getenv("PORT", "8080"))
FRONTEND_PATH = os.getenv("FRONTEND_PATH")


# CORS設定
ORIGINS = [org for org in os.getenv("ORIGINS", "").split(",") if org]

# IPアクセス制限
ALLOWED_IPS = os.getenv("ALLOWED_IPS")

# ===== Google Cloud 設定 =====
VERTEX_PROJECT = os.getenv("VERTEX_PROJECT")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION")
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
# ===== Secret Manager設定 ===== 環境変数から取得する場合があるので空白許容
SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY = os.getenv(
    "SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY", ""
)

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
        logger.debug(f"Secret Managerから{secret_id}を取得しています")

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
            logger.debug(
                "環境変数にGoogle Maps APIキーが設定されているため、ファイルから取得します"
            )
            api_key = f.read()
    else:
        logger.debug(
            "環境変数にGoogle Maps APIキーが設定されていないため、Secret Managerから取得します"
        )
        api_key = access_secret(SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY)
        if not api_key:
            raise Exception("Google Maps APIキーが見つかりません")
    return api_key




def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からAPIキーを取得する"""
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, "")


def limit_remote_addr(request: Request):
    # クライアント直前のIPアドレスを取得（TCPコネクションのリモートIP）
    client_ip = request.client.host if request.client else None
    logger.debug("接続直前のIPアドレス: %s", client_ip)

    # X-Forwarded-For ヘッダーを取得（転送途中の経路で使われるケースが多い）
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    logger.debug("X-Forwarded-For ヘッダー全体: %s", forwarded_for)

    if forwarded_for:
        # ヘッダーに複数のIPが含まれている場合、カンマで分割
        forwarded_ips = [ip.strip() for ip in forwarded_for.split(",")]
        logger.debug("転送途中のIPアドレスリスト: %s", forwarded_ips)
        # 最初のIPアドレスをオリジナルのクライアントIPとする
        original_ip = forwarded_ips[0]
        logger.debug("最初のIPアドレス (オリジナル): %s", original_ip)
        # チェック処理はここでは原則として最初のIPを利用する
        remote_addr = original_ip
    else:
        remote_addr = client_ip

    logger.debug("検証対象のIPアドレス: %s", remote_addr)

    # 既存のIP形式の検証と許可リストチェック
    try:
        client_ip_obj = ipaddress.ip_address(remote_addr)
        logger.debug("IPアドレス検証済み: %s", client_ip_obj)
    except ValueError:
        time.sleep(0.05)
        raise HTTPException(status_code=400, detail="不正なIPアドレス形式です")

    allowed_tokens = ALLOWED_IPS
    logger.debug("許可されたIP設定: %s", allowed_tokens)
    allowed_networks = []
    for token in allowed_tokens.split(","):
        token = token.strip()
        if token:
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
                logger.error("無効なIPまたはネットワーク: %s, エラー: %s", token, e)

    for network in allowed_networks:
        if client_ip_obj in network:
            return

    time.sleep(0.05)
    raise HTTPException(status_code=403, detail="アクセスが許可されていません")
