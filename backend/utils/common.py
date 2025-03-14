# utils/common.py
import logging
import os
import json
from typing import Optional
from functools import wraps
from dotenv import load_dotenv
from copy import copy
from uuid import uuid4

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


# リクエストIDの生成機能
def generate_request_id(prefix="B"):
    """
    プレフィックス + uuid4の先頭12桁からなるリクエストIDを生成する

    Args:
        prefix (str): IDのプレフィックス。デフォルトは"B"（バックエンド）

    Returns:
        str: 生成されたリクエストID (プレフィックス + 12桁のuuid)
    """
    return f"{prefix}{uuid4().hex[:12]}"


def wrap_asyncgenerator_logger(meta_info: dict = {}):
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


def create_dict_logger(input_dict: dict = {}, meta_info: dict = {}):
    """
    辞書にメタ情報を追加してログ出力する関数を生成する

    Args:
        meta_info (dict): ログに追加する追加情報の辞書

    Returns:
        function: 辞書を受け取り、meta_infoと結合してログ出力し、結合した辞書を返す関数
    """
    enriched_dict = copy(meta_info)
    enriched_dict.update(input_dict)

    # 更新された辞書をログ出力
    logger.info(enriched_dict)

    # 更新された辞書を返す
    return enriched_dict


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


def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からAPIキーを取得する"""
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, "")
