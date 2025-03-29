# utils/logger.py
import logging
import os
import json
from typing import Dict, List, Any
from copy import copy
from fastapi import Request
from functools import wraps

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


def sanitize_request_data(
    data: Any, max_length: int = 65536, sensitive_keys: List[str] = []
) -> Any:
    """
    リクエストデータから機密情報を削除する関数

    Args:
        data (Any): サニタイズするデータ
        max_length : 最大文字数。Falseに評価されるときは無限
        sensitive_keys (List[str]): 機密キーのリスト（省略可）


    Returns:
        Any: サニタイズされたデータ
    """
    try:
        data = json.loads(data)
    except:
        pass
    if (
        max_length
        and isinstance(data, (str, bytes, bytearray))
        and len(data) > max_length
    ):
        if isinstance(data, str):
            return data[:max_length] + "[TRUNCATED]"
        elif isinstance(data, (bytes, bytearray)):
            # バイナリデータを文字列に変換してから切り詰める
            try:
                # UTF-8でデコードを試みる
                return (
                    data.decode("utf-8", errors="replace")[:max_length] + "[TRUNCATED]"
                )
            except Exception:
                # デコードに失敗した場合はbyteアレイのまま
                return data[:max_length] + b"[TRUNCATED]"
    elif isinstance(data, (bytes, bytearray)):
        # 長さが制限を超えていなくても、バイナリデータは文字列に変換
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.hex()
    elif isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if isinstance(key, str) and any(
                s_key in key.lower() for s_key in sensitive_keys
            ):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, (dict, list, str, bytes, bytearray)):
                sanitized[key] = sanitize_request_data(
                    value, max_length=max_length, sensitive_keys=sensitive_keys
                )
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, list):
        return [
            sanitize_request_data(
                item, max_length=max_length, sensitive_keys=sensitive_keys
            )
            for item in data
        ]
    else:
        return data


async def log_request(request: Request, current_user: Dict | None, log_max_length: int):

    request_info = {
        "event": "request_received",
        "X-Request-Id": request.headers.get("X-Request-Id", ""),
        "email": (
            current_user.get("email", "unknown")
            if isinstance(current_user, dict)
            else ""
        ),
        "path": request.url.path,
        "method": request.method,
        "client": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "request_body": await request.body(),
    }

    # 受けたリクエストの情報をロガー表示する
    logger.info(
        sanitize_request_data(
            request_info,
            log_max_length,
        )
    )
    return request_info


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
                streaming_log["chunk"] = sanitize_request_data(
                    chunk, max_length=max_length
                )

                # ログ出力
                logger.info(streaming_log)

                # 元のチャンクを次の処理へ渡す（切り詰めたのはログ用だけ）
                yield chunk

        return wrapper

    return decorator


def create_dict_logger(
    input_dict: dict = {},
    meta_info: dict = {},
    max_length: int = 1000,
    sensitive_keys: List[str] = [],
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
    truncated_input = sanitize_request_data(
        input_dict, max_length=max_length, sensitive_keys=sensitive_keys
    )

    # 切り詰めた辞書をenriched_dictに追加
    enriched_dict.update(truncated_input)

    # 更新された辞書をログ出力
    logger.info(enriched_dict)

    # 更新された辞書を返す
    return input_dict
