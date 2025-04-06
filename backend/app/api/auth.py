# API ルート: auth.py - 認証関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from firebase_admin import auth
from typing import Dict, Any, Callable
import re
import time
import os
from functools import partial
from common_utils.logger import logger, sanitize_request_data, create_dict_logger, log_request
from fastapi.middleware.cors import CORSMiddleware

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# ロギング設定
LOGOUT_LOG_MAX_LENGTH = int(os.environ["LOGOUT_LOG_MAX_LENGTH"])
VERIFY_AUTH_LOG_MAX_LENGTH = int(os.environ["VERIFY_AUTH_LOG_MAX_LENGTH"])
MIDDLE_WARE_LOG_MAX_LENGTH = int(os.environ["MIDDLE_WARE_LOG_MAX_LENGTH"])
SENSITIVE_KEYS = os.environ["SENSITIVE_KEYS"].split(",")

# リクエストIDが不要なパス
UNNEED_REQUEST_ID_PATH = os.environ.get("UNNEED_REQUEST_ID_PATH", "").split(",")
UNNEED_REQUEST_ID_PATH_STARTSWITH = os.environ.get("UNNEED_REQUEST_ID_PATH_STARTSWITH", "").split(",")
UNNEED_REQUEST_ID_PATH_ENDSWITH = os.environ.get("UNNEED_REQUEST_ID_PATH_ENDSWITH", "").split(",")

router = APIRouter()

# センシティブ情報のマスク処理
sanitize_request_data = partial(sanitize_request_data, sensitive_keys=SENSITIVE_KEYS)
create_dict_logger = partial(create_dict_logger, sensitive_keys=SENSITIVE_KEYS)

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

# ログリクエストミドルウェア
async def log_request_middleware(request: Request, call_next: Callable) -> JSONResponse:
    # OPTIONSリクエストの場合はリクエストIDのチェックをスキップ
    # URLパスの取得
    path: str = request.url.path
    # OPTIONSリクエスト、静的アセット、viteのアイコンへのリクエストは処理をスキップ
    if request.method == "OPTIONS":
        return await call_next(request)

    # リクエストヘッダーからリクエストIDを取得
    request_id: str = request.headers.get("X-Request-Id", "")

    # リクエストIDのバリデーション (Fで始まる12桁の16進数)
    # ルートパス以外のアクセスでリクエストIDが無効な場合はエラーを返す
    if (
        not path == "/"
        and not any(path == unneed for unneed in UNNEED_REQUEST_ID_PATH)
        and not any(
            path.startswith(unneed) for unneed in UNNEED_REQUEST_ID_PATH_STARTSWITH
        )
        and not any(path.endswith(unneed) for unneed in UNNEED_REQUEST_ID_PATH_ENDSWITH)
        and not (request_id and re.match(r"^F[0-9a-f]{12}$", request_id))
    ):
        # エラー情報をログに記録
        logger.debug("エラー処理")
        logger.error(
            sanitize_request_data(
                {
                    "event": "invalid_request_id",
                    "path": request.url.path,
                    "method": request.method,
                    "client": request.client.host if request.client else "unknown",
                    "request_id": request_id,
                },
                MIDDLE_WARE_LOG_MAX_LENGTH,
            )
        )

        # 不正なリクエストIDの場合、403 Forbiddenを返す
        return JSONResponse(
            status_code=403, content={"error": "無効なリクエストIDです"}
        )
    start_time: float = time.time()

    # リクエストの基本情報を収集してロギング
    # URLパスの取得
    path = request.url.path
    # HTTPメソッドの取得
    method: str = request.method
    # クライアントのIPアドレスを取得（取得できない場合は"unknown"）
    client_host: str = request.client.host if request.client else "unknown"
    # リクエストボディの取得とデコード
    body: bytes = await request.body()
    # ボディデータを指定された最大長に制限してデコード
    decoded_data: str = body.decode("utf-8")

    # リクエスト受信時の詳細情報をログに記録
    # - リクエストID、パス、メソッド、クライアントIP
    # - ユーザーエージェント、リクエストボディを含む
    logger.debug("リクエスト受信")
    logger.debug(
        sanitize_request_data(
            {
                "event": "request_received",
                "X-Request-Id": request_id,
                "path": path,
                "method": method,
                "client": client_host,
                "user_agent": request.headers.get("user-agent", "unknown"),
                # "request_body": decoded_data,
            },
            MIDDLE_WARE_LOG_MAX_LENGTH,
        )
    )

    # 次の処理へ
    response: JSONResponse = await call_next(request)

    # 処理時間の計算
    process_time: float = time.time() - start_time

    # レスポンス情報のロギング
    logger.debug("リクエスト処理終了")
    logger.debug(
        sanitize_request_data(
            {
                "event": "request_completed",
                "X-Request-Id": request_id,
                "path": path,
                "method": method,
                "status_code": response.status_code,
                "process_time_sec": round(process_time, 4),
            },
            MIDDLE_WARE_LOG_MAX_LENGTH,
        )
    )

    return response

@router.get("/verify-auth")
async def verify_auth(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        logger.debug("認証検証開始")
        logger.debug("トークンの復号化成功。ユーザー: %s", current_user.get("email"))
        request_info: Dict[str, Any] = await log_request(
            request, current_user, VERIFY_AUTH_LOG_MAX_LENGTH
        )

        response_data: Dict[str, Any] = {
            "status": "success",
            "user": {
                "email": current_user.get("email"),
                "uid": current_user.get("uid"),
            },
            "expire_time": current_user.get("exp"),
        }
        logger.debug("認証検証完了")
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=VERIFY_AUTH_LOG_MAX_LENGTH,
        )
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/logout")
async def logout(request: Request) -> Dict[str, str]:
    try:
        request_info: Dict[str, Any] = await log_request(request, None, LOGOUT_LOG_MAX_LENGTH)

        logger.debug("ログアウト処理開始")

        response_data: Dict[str, str] = {"status": "success", "message": "ログアウトに成功しました"}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path")
                if k in request_info
            },
            max_length=LOGOUT_LOG_MAX_LENGTH,
        )
    except Exception as e:
        logger.error("ログアウト処理中にエラーが発生: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))