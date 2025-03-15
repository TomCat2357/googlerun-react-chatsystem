# utils/common.py
import logging
import os
import json
from typing import List, Any, Optional
from functools import wraps
from dotenv import load_dotenv
from copy import copy
from uuid import uuid4
from fastapi import Request

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

# 非同期ジェネレーター用ログ最大値
GEOCODING_LOG_MAX_LENGTH = int(os.getenv("GEOCODING_LOG_MAX_LENGTH"))
CHAT_LOG_MAX_LENGTH = int(os.getenv("CHAT_LOG_MAX_LENGTH"))

# 辞書ロガー用最大値
CONFIG_LOG_MAX_LENGTH = int(os.getenv("CONFIG_LOG_MAX_LENGTH"))
VERIFY_AUTH_LOG_MAX_LENGTH = int(os.getenv("VERIFY_AUTH_LOG_MAX_LENGTH"))
SPEECH2TEXT_LOG_MAX_LENGTH = int(os.getenv("SPEECH2TEXT_LOG_MAX_LENGTH"))
GENERATE_IMAGE_LOG_MAX_LENGTH = int(os.getenv("GENERATE_IMAGE_LOG_MAX_LENGTH"))
LOGOUT_LOG_MAX_LENGTH = int(os.getenv("LOGOUT_LOG_MAX_LENGTH"))

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


def limit_nested_data(data: any, max_length: int = 65536) -> any:
    """
    data に対して再帰的に処理を行い、max_length に基づいて長さを制限する関数。

    Args:
        data: 処理対象のオブジェクト。
        max_length: 長さの制限値 (デフォルトは 65536)。

    Returns:
        処理後のオブジェクト。
    """

    if isinstance(data, (str, bytes)):
        return data[:max_length]
    elif isinstance(data, (list, set)):
        return type(data)(limit_nested_data(item, max_length) for item in data)
    elif isinstance(data, dict):
        return {
            key: limit_nested_data(value, max_length) for key, value in data.items()
        }
    else:
        return data


def wrap_asyncgenerator_logger(
    meta_info: dict = {}, max_length: int = 1000
) -> callable:
    """
    非同期ジェネレーター関数をラップしてログ出力を追加するデコレータ関数

    Args:
        meta_info: ログに追加する追加情報の辞書

    Returns:
        decorator: ラップする非同期ジェネレーター関数を受け取るデコレータ関数
    """

    def decorator(generator_func: callable) -> callable:
        @wraps(generator_func)
        async def wrapper(*args, **kwargs) -> any:
            # 元のジェネレーター関数を実行し、各チャンクを処理
            async for chunk in generator_func(*args, **kwargs):
                # ログ用の辞書を準備（meta_infoのディープコピーまたは新規辞書）
                if isinstance(meta_info, dict):
                    streaming_log = copy(meta_info)
                else:
                    streaming_log = {}

                # chunkの長さを制限する
                streaming_log["chunk"] = limit_nested_data(chunk, max_length=max_length)

                # ログ出力
                logger.info(streaming_log)

                # 元のチャンクを次の処理へ渡す（切り詰めたのはログ用だけ）
                yield chunk

        return wrapper

    return decorator


def create_dict_logger(
    input_dict: dict = {}, meta_info: dict = {}, max_length: int = 1000
) -> dict:
    """
    辞書にメタ情報を追加してログ出力する関数を生成する
    長いテキスト値は指定された長さに切り詰める

    Args:
        input_dict (dict): ログに出力する辞書
        meta_info (dict): ログに追加する追加情報の辞書

    Returns:
        dict: 結合した辞書
    """
    enriched_dict = copy(meta_info)

    # input_dictの各値を処理して長すぎる場合は切り詰める
    truncated_input = limit_nested_data(input_dict, max_length=max_length)

    # 切り詰めた辞書をenriched_dictに追加
    enriched_dict.update(truncated_input)

    # 更新された辞書をログ出力
    logger.info(enriched_dict)

    # 更新された辞書を返す
    return enriched_dict


def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からAPIキーを取得する"""
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, "")


async def log_request(
    request: Request, request_body: Optional[Any] = None, max_length: int = 1000
):
    """
    リクエスト情報をログに記録する共通の依存関係関数

    Args:
        request (Request): FastAPIのRequestオブジェクト
        request_body (Optional[Any]): リクエストボディ（Pydanticモデルなど）
        max_length (int): ログの最大長

    Returns:
        str: リクエストID
    """
    request_id = request.headers.get("X-Request-Id", "")

    # パスからエンドポイント名を抽出（例: "/backend/chat" → "chat"）
    path = request.url.path
    endpoint_name = path.split("/")[-1] if "/" in path else path

    # リクエスト情報をログに記録
    log_data = {
        "event": "endpoint_request",
        "endpoint": endpoint_name,
        "path": path,
        "method": request.method,
        "X-Request-Id": request_id,
        "client": request.client.host if request.client else "unknown",
    }

    # リクエストボディが提供されている場合はログに追加
    if request_body is not None:
        try:
            # dict形式に変換（Pydanticのモデルの場合）
            if hasattr(request_body, "dict"):
                body_dict = request_body.dict()
            else:
                body_dict = request_body

            # 機密データをサニタイズ
            sanitized_body = sanitize_request_data(body_dict)

            # サイズが大きい場合は特別処理
            if isinstance(sanitized_body, dict):
                # 特定のフィールドの長さを確認（例：messages、promptなど）
                for field_name in ["messages", "prompt", "audio_data", "files"]:
                    if field_name in sanitized_body and isinstance(
                        sanitized_body[field_name], list
                    ):
                        items_count = len(sanitized_body[field_name])
                        if items_count > 10:  # 10個以上の項目がある場合
                            # 最初と最後の数項目だけを保持
                            first_items = sanitized_body[field_name][:3]
                            last_items = (
                                sanitized_body[field_name][-2:]
                                if items_count > 5
                                else []
                            )
                            sanitized_body[field_name] = [
                                *first_items,
                                f"... {items_count - len(first_items) - len(last_items)} items omitted ...",
                                *last_items,
                            ]

            log_data["body"] = sanitized_body

        except Exception as e:
            # リクエストボディの処理中にエラーが発生した場合
            log_data["body_error"] = f"リクエストボディの処理中にエラー: {str(e)}"

    # 長さ制限を適用
    truncated_log = limit_nested_data(log_data, max_length=max_length)

    # 切り詰めが行われたかを確認
    original_size = len(str(log_data))
    truncated_size = len(str(truncated_log))

    if original_size != truncated_size:
        truncated_log["_truncated"] = True
        truncated_log["_original_size"] = original_size

    logger.info(truncated_log)

    # リクエストIDを返す
    return request_id


def log_request_body(
    request_id: str, endpoint_name: str, body: any, max_length: int = 1000
) -> None:
    """
    リクエストボディを安全にログに記録する関数

    Args:
        request_id (str): リクエストID
        endpoint_name (str): エンドポイント名
        body (any): ログに記録するリクエストボディ（機密データは処理済みであること）
        max_length (int): ログの最大長
    """
    try:
        log_data = {
            "event": "request_body",
            "X-Request-Id": request_id,
            "endpoint": endpoint_name,
            "body": body,
        }

        # 長いデータを制限
        truncated_log = limit_nested_data(log_data, max_length=max_length)
        logger.info(truncated_log)
    except Exception as e:
        logger.error(f"リクエストボディのログ記録中にエラー: {str(e)}", exc_info=True)


def sanitize_request_data(data: Any, sensitive_keys: List[str] = None) -> Any:
    """
    リクエストデータから機密情報を削除する関数

    Args:
        data (Any): サニタイズするデータ
        sensitive_keys (List[str]): 機密キーのリスト（省略可）

    Returns:
        Any: サニタイズされたデータ
    """
    if sensitive_keys is None:
        sensitive_keys = ["authorization", "token", "password", "secret", "api_key"]

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if isinstance(key, str) and any(
                s_key in key.lower() for s_key in sensitive_keys
            ):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, (dict, list)):
                sanitized[key] = sanitize_request_data(value, sensitive_keys)
            elif isinstance(value, str) and len(value) > 1000:
                # 長い文字列は切り詰める
                if key.lower() in ["audio_data", "image", "content", "prompt"]:
                    sanitized[key] = f"[BINARY_DATA: {len(value)} chars]"
                else:
                    sanitized[key] = value[:100] + "... [truncated]"
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, list):
        return [sanitize_request_data(item, sensitive_keys) for item in data]
    else:
        return data
