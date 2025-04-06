#%%
# 修正後のapp.py全文

from utils.geocoding_service import get_google_maps_api_key, process_optimized_geocode

from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any, List, Optional, Callable, AsyncGenerator, Tuple, Union, cast
from firebase_admin import auth, credentials, firestore
import firebase_admin
from pydub import AudioSegment
import os, json, asyncio, base64, time, re, io, datetime, hashlib, math
from google.cloud import storage, pubsub_v1
from utils.chat_utils import common_message_function
from utils.speech2text import transcribe_streaming_v2
from utils.generate_image import generate_image
from functools import partial
from google.cloud import storage, firestore
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
)
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

from common_utils.logger import (
    logger,
    wrap_asyncgenerator_logger,
    create_dict_logger,
    sanitize_request_data,
    log_request,
    DEBUG,
)

from common_utils.class_types import (
    GeocodeRequest,
    ChatRequest,
    SpeechToTextRequest,
    GenerateImageRequest,
    WhisperUploadRequest,
    WhisperFirestoreData,
    WhisperPubSubMessageData
)

# ===== アプリケーション設定 =====
PORT = int(os.environ.get("PORT", "8080"))
FRONTEND_PATH = os.environ["FRONTEND_PATH"]

# CORS設定
ORIGINS = [org for org in os.environ.get("ORIGINS", "").split(",") if org]

# IPアクセス制限
ALLOWED_IPS = os.environ.get("ALLOWED_IPS")

# ===== Google Cloud 設定 =====
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCP_REGION = os.environ["GCP_REGION"]

# ===== Firebase設定 =====
FIREBASE_CLIENT_SECRET_PATH = os.environ.get("FIREBASE_CLIENT_SECRET_PATH", "")

# ===== SSL/TLS設定 =====
# Cloud RunではSSL証明書を使用しないため、空白許容
SSL_CERT_PATH = os.environ.get("SSL_CERT_PATH", "")
SSL_KEY_PATH = os.environ.get("SSL_KEY_PATH", "")

# ===== API制限設定 =====
# シークレットサービスから取得する場合があるため、空白許容
GOOGLE_MAPS_API_KEY_PATH = os.environ.get("GOOGLE_MAPS_API_KEY_PATH", "")
GOOGLE_MAPS_API_CACHE_TTL = int(os.environ["GOOGLE_MAPS_API_CACHE_TTL"])
GEOCODING_NO_IMAGE_MAX_BATCH_SIZE = int(os.environ["GEOCODING_NO_IMAGE_MAX_BATCH_SIZE"])
GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE = int(os.environ["GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE"])
# 並行処理のバッチサイズ（追加）
GEOCODING_BATCH_SIZE = int(os.environ.get("GEOCODING_BATCH_SIZE", "5"))

# ===== Secret Manager設定 ===== 環境変数から取得する場合があるので空白許容
SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY = os.environ.get("SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY", "")

# ===== データ制限設定 =====
MAX_IMAGES = int(os.environ["MAX_IMAGES"])
MAX_LONG_EDGE = int(os.environ["MAX_LONG_EDGE"])
MAX_IMAGE_SIZE = int(os.environ["MAX_IMAGE_SIZE"])
MAX_AUDIO_FILES = int(os.environ["MAX_AUDIO_FILES"])
MAX_TEXT_FILES = int(os.environ["MAX_TEXT_FILES"])
SPEECH_MAX_SECONDS = int(os.environ["SPEECH_MAX_SECONDS"])

# ===== モデル設定 =====
MODELS = os.environ["MODELS"]

# Imagen設定
IMAGEN_MODELS = os.environ["IMAGEN_MODELS"]
IMAGEN_NUMBER_OF_IMAGES = os.environ["IMAGEN_NUMBER_OF_IMAGES"]
IMAGEN_ASPECT_RATIOS = os.environ["IMAGEN_ASPECT_RATIOS"]
IMAGEN_LANGUAGES = os.environ["IMAGEN_LANGUAGES"]
IMAGEN_ADD_WATERMARK = os.environ["IMAGEN_ADD_WATERMARK"]
IMAGEN_SAFETY_FILTER_LEVELS = os.environ["IMAGEN_SAFETY_FILTER_LEVELS"]
IMAGEN_PERSON_GENERATIONS = os.environ["IMAGEN_PERSON_GENERATIONS"]

# 非同期ジェネレーター用ログ最大値
GEOCODING_LOG_MAX_LENGTH = int(os.environ["GEOCODING_LOG_MAX_LENGTH"])
CHAT_LOG_MAX_LENGTH = int(os.environ["CHAT_LOG_MAX_LENGTH"])

# 辞書ロガー用最大値
CONFIG_LOG_MAX_LENGTH = int(os.environ["CONFIG_LOG_MAX_LENGTH"])
VERIFY_AUTH_LOG_MAX_LENGTH = int(os.environ["VERIFY_AUTH_LOG_MAX_LENGTH"])
SPEECH2TEXT_LOG_MAX_LENGTH = int(os.environ["SPEECH2TEXT_LOG_MAX_LENGTH"])
GENERATE_IMAGE_LOG_MAX_LENGTH = int(os.environ["GENERATE_IMAGE_LOG_MAX_LENGTH"])
LOGOUT_LOG_MAX_LENGTH = int(os.environ["LOGOUT_LOG_MAX_LENGTH"])
MIDDLE_WARE_LOG_MAX_LENGTH = int(os.environ["MIDDLE_WARE_LOG_MAX_LENGTH"])
GENERAL_LOG_MAX_LENGTH = int(os.environ["GENERAL_LOG_MAX_LENGTH"])

# request_idを必要としないパス。重要性が低いので未設定許容
UNNEED_REQUEST_ID_PATH = os.environ.get("UNNEED_REQUEST_ID_PATH", "").split(",")
UNNEED_REQUEST_ID_PATH_STARTSWITH = os.environ.get("UNNEED_REQUEST_ID_PATH_STARTSWITH", "").split(",")
UNNEED_REQUEST_ID_PATH_ENDSWITH = os.environ.get("UNNEED_REQUEST_ID_PATH_ENDSWITH", "").split(",")

# ログでマスクするセンシティブ情報。設定しなければエラーがでる
SENSITIVE_KEYS = os.environ["SENSITIVE_KEYS"].split(",")

# GCS関連の設定
GCS_BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
PUBSUB_TOPIC = os.environ["PUBSUB_TOPIC"]
BATCH_IMAGE_URL = os.environ["BATCH_IMAGE_URL"]
EMAIL_NOTIFICATION = bool(os.environ.get("EMAIL_NOTIFICATION", False))

# ===== Firestore コレクション設定 =====
WHISPER_JOBS_COLLECTION = os.environ["WHISPER_JOBS_COLLECTION"]
WHISPER_MAX_SECONDS = int(os.environ["WHISPER_MAX_SECONDS"])

# FirestoreのSERVER_TIMESTAMPをJSONに変換するためのカスタムエンコーダー
class FirestoreEncoder(json.JSONEncoder):
    def default(self, obj):
        if obj == firestore.SERVER_TIMESTAMP:
            return {"__special__": "SERVER_TIMESTAMP"}
        return super().default(obj)

# モデル名からAPIキーを取得する関数
def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からAPIキーを取得する"""
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.environ.get("MODEL_API_KEYS", "{}")).get(source, "")

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


firebase_db: firestore.Client = firestore.Client()

# センシティブ情報は先に登録しておく
sanitize_request_data = partial(sanitize_request_data, sensitive_keys=SENSITIVE_KEYS)
create_dict_logger = partial(create_dict_logger, sensitive_keys=SENSITIVE_KEYS)

# Firebase Admin SDKの初期化
try:
    # 初期化されているかチェック
    firebase_admin.get_app()
    logger.debug("Firebase既に初期化済み")
except ValueError:
    # 初期化されていない場合のみ初期化
    if os.path.exists(FIREBASE_CLIENT_SECRET_PATH):
        logger.debug(f"Firebase認証情報を読み込み: {FIREBASE_CLIENT_SECRET_PATH}")
        cred: credentials.Certificate = credentials.Certificate(FIREBASE_CLIENT_SECRET_PATH)
        firebase_admin.initialize_app(cred)  # 名前を指定しない
    else:
        logger.debug("Firebase認証情報なしで初期化")
        firebase_admin.initialize_app()  # 名前を指定しない


# FastAPIアプリケーションの初期化
app: FastAPI = FastAPI()

logger.debug("ORIGINS: %s", ORIGINS)

# FastAPIのCORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-Id"],
    expose_headers=["Authorization"],
)


@app.middleware("http")
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


@app.post("/backend/geocoding")
async def geocoding_endpoint(
    request: Request,
    geocoding_request: GeocodeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """
    ジオコーディングのための最適化されたRESTfulエンドポイント
    クライアントからキャッシュ情報を受け取り、
    最小限のAPI呼び出しで結果と画像を取得する
    """
    # リクエストの情報を取得
    request_info: Dict[str, Any] = await log_request(request, current_user, GEOCODING_LOG_MAX_LENGTH)
    logger.debug("リクエスト情報: %s", request_info)

    mode: str = geocoding_request.mode
    lines = geocoding_request.lines
    options = geocoding_request.options

    # 上限件数のチェック
    max_batch_size: int = (
        GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE
        if options.get("showSatellite") or options.get("showStreetView")
        else GEOCODING_NO_IMAGE_MAX_BATCH_SIZE
    )

    if len(lines) > max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"入力された件数は{len(lines)}件ですが、1回の送信で取得可能な上限は{max_batch_size}件です。",
        )

    google_maps_api_key: str = get_google_maps_api_key()
    timestamp: int = int(time.time() * 1000)

    # クエリの重複を排除し、元のインデックスを保持
    unique_queries: Dict[str, Dict[str, Any]] = {}
    for idx, line_data in enumerate(lines):
        query: str = line_data.query
        if query not in unique_queries:
            # 最初に出現したクエリの情報をコピー
            unique_queries[query] = {"data": line_data, "indices": [idx]}
        else:
            # 既存のクエリに元のインデックスを追加
            unique_queries[query]["indices"].append(idx)

    logger.debug(f"重複排除後のクエリ数: {len(unique_queries)} (元: {len(lines)})")

    # StreamingResponseを使って結果を非同期的に返す
    @wrap_asyncgenerator_logger(
        meta_info={
            key: request_info[key]
            for key in ("X-Request-Id", "path", "email")
            if key in request_info
        },
        max_length=GEOCODING_LOG_MAX_LENGTH,
    )
    async def generate_results() -> AsyncGenerator[str, None]:
        # 並行処理用のタスクリスト
        tasks: List[asyncio.Task] = []

        # 重複排除したクエリごとにタスクを作成
        for query, query_info in unique_queries.items():
            line_data = query_info["data"]
            original_indices: List[int] = query_info["indices"]

            # 処理タスクを作成
            task: asyncio.Task = process_optimized_geocode(
                original_indices=original_indices,
                query=query,
                mode=mode,
                api_key=google_maps_api_key,
                timestamp=timestamp,
                options=options,
                has_geocode_cache=line_data.has_geocode_cache,
                has_satellite_cache=line_data.has_satellite_cache,
                has_streetview_cache=line_data.has_streetview_cache,
                cached_lat=line_data.latitude,
                cached_lng=line_data.longitude,
            )
            tasks.append(task)

        # 並行実行（ただし、レート制限を考慮して一度に実行するタスク数を制限）
        chunk_size: int = GEOCODING_BATCH_SIZE
        total_chunks: int = (len(tasks) + chunk_size - 1) // chunk_size
        processed_chunks: int = 0

        for i in range(0, len(tasks), chunk_size):
            chunk: List[asyncio.Task] = tasks[i : i + chunk_size]
            chunk_results: List[List[str]] = await asyncio.gather(*chunk)
            processed_chunks += 1

            # 進捗計算
            progress_base: int = int((processed_chunks / total_chunks) * 100)

            # 結果を順番に返す
            for result_chunks in chunk_results:
                for result_chunk in result_chunks:
                    # 進捗情報を埋め込み
                    try:
                        chunk_data: Dict[str, Any] = json.loads(result_chunk.rstrip())
                        if (
                            "payload" in chunk_data
                            and "progress" in chunk_data["payload"]
                        ):
                            if chunk_data["payload"]["progress"] == -1:
                                chunk_data["payload"]["progress"] = progress_base
                            yield json.dumps(chunk_data) + "\n"
                        else:
                            yield result_chunk
                    except:
                        yield result_chunk

            # APIレート制限対策の待機
            if i + chunk_size < len(tasks):
                await asyncio.sleep(1)

        # 全ての処理が完了したことを通知
        yield json.dumps({"type": "COMPLETE", "payload": {}}) + "\n"

    return StreamingResponse(
        generate_results(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Transfer-Encoding": "chunked"},
    )


@app.get("/backend/config")
async def get_config(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GEOCODING_LOG_MAX_LENGTH
        )
        logger.debug("リクエスト情報: %s", request_info)

        config_values: Dict[str, Any] = {
            "MAX_IMAGES": MAX_IMAGES,
            "MAX_AUDIO_FILES": MAX_AUDIO_FILES,
            "MAX_TEXT_FILES": MAX_TEXT_FILES,
            "MAX_LONG_EDGE": MAX_LONG_EDGE,
            "MAX_IMAGE_SIZE": MAX_IMAGE_SIZE,
            "GOOGLE_MAPS_API_CACHE_TTL": GOOGLE_MAPS_API_CACHE_TTL,
            "GEOCODING_NO_IMAGE_MAX_BATCH_SIZE": GEOCODING_NO_IMAGE_MAX_BATCH_SIZE,
            "GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE": GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE,
            "SPEECH_MAX_SECONDS": SPEECH_MAX_SECONDS,
            "MODELS": MODELS,
            "IMAGEN_MODELS": IMAGEN_MODELS,
            "IMAGEN_NUMBER_OF_IMAGES": IMAGEN_NUMBER_OF_IMAGES,
            "IMAGEN_ASPECT_RATIOS": IMAGEN_ASPECT_RATIOS,
            "IMAGEN_LANGUAGES": IMAGEN_LANGUAGES,
            "IMAGEN_ADD_WATERMARK": IMAGEN_ADD_WATERMARK,
            "IMAGEN_SAFETY_FILTER_LEVELS": IMAGEN_SAFETY_FILTER_LEVELS,
            "IMAGEN_PERSON_GENERATIONS": IMAGEN_PERSON_GENERATIONS,
            "WHISPER_MAX_SECONDS" : WHISPER_MAX_SECONDS,
        }
        logger.debug("Config取得成功")
        return create_dict_logger(
            config_values,
            meta_info={
                key: request_info[key]
                for key in ("X-Request-Id", "path", "email")
                if key in request_info
            },
            max_length=CONFIG_LOG_MAX_LENGTH,
        )
    except Exception as e:
        logger.error("Config取得エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backend/verify-auth")
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


@app.post("/backend/chat")
async def chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    logger.debug("チャットリクエストを処理中")
    try:
        request_info: Dict[str, Any] = await log_request(request, current_user, CHAT_LOG_MAX_LENGTH)
        logger.debug("リクエスト情報: %s", request_info)

        messages: List[Dict[str, Any]] = chat_request.messages
        model: str = chat_request.model
        logger.debug(f"モデル: {model}")

        if model is None:
            raise HTTPException(
                status_code=400, detail="モデル情報が提供されていません"
            )

        model_api_key: str = get_api_key_for_model(model)

        # メッセージ変換処理のログ出力を追加
        transformed_messages: List[Dict[str, Any]] = []
        for msg in messages:
            # ユーザーメッセージに添付ファイルがある場合の処理
            if msg.get("role") == "user":
                # ファイルデータの処理とログ出力
                if "files" in msg and msg["files"]:
                    file_types: List[str] = []
                    for file in msg["files"]:
                        mime_type: str = file.get("mimeType", "")
                        name: str = file.get("name", "")
                        file_types.append(f"{name} ({mime_type})")
                    logger.debug(f"添付ファイル: {', '.join(file_types)}")

                # メッセージをそのまま追加（prepare_message_for_aiは使わない）
                transformed_messages.append(msg)
            else:
                # システムメッセージまたはアシスタントメッセージはそのまま
                transformed_messages.append(msg)
        logger.debug(f"選択されたモデル: {model}")

        # プロンプト内容の概要をログに出力
        for i, msg in enumerate(transformed_messages):
            role: str = msg.get("role", "unknown")
            content: Union[str, List[Dict[str, Any]]] = msg.get("content", "")

            if isinstance(content, str):
                content_preview: str = content[:50] + "..." if len(content) > 50 else content
                logger.debug(f"メッセージ[{i}]: role={role}, content={content_preview}")
            elif isinstance(content, list):
                parts_info: List[str] = []
                for part in content:
                    if part.get("type") == "text":
                        text: str = (
                            part.get("text", "")[:20] + "..."
                            if len(part.get("text", "")) > 20
                            else part.get("text", "")
                        )
                        parts_info.append(f"text: {text}")
                    elif part.get("type") == "image_url":
                        parts_info.append("image")
                logger.debug(f"メッセージ[{i}]: role={role}, parts={parts_info}")

        # ストリーミングレスポンスの作成
        @wrap_asyncgenerator_logger(
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=CHAT_LOG_MAX_LENGTH,
        )
        async def generate_stream() -> AsyncGenerator[str, None]:
            for chunk in common_message_function(
                model=model,
                stream=True,
                messages=transformed_messages,
                api_key=model_api_key,
            ):
                yield chunk

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Transfer-Encoding": "chunked"},
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error("チャットエラー: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backend/speech2text")
async def speech2text(
    request: Request,
    speech_request: SpeechToTextRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    logger.debug("音声認識処理開始")
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, VERIFY_AUTH_LOG_MAX_LENGTH
        )

        audio_data: str = speech_request.audio_data

        if not audio_data:
            logger.error("音声データが見つかりません")
            raise HTTPException(
                status_code=400, detail="音声データが提供されていません"
            )

        # ヘッダー除去（"data:audio/～;base64,..."形式の場合）
        if audio_data.startswith("data:"):
            _, audio_data = audio_data.split(",", 1)

        try:
            audio_bytes: bytes = base64.b64decode(audio_data)
            logger.debug(f"受信した音声サイズ: {len(audio_bytes) / 1024:.2f} KB")
        except Exception as e:
            logger.error(f"音声データのBase64デコードエラー: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"音声データの解析に失敗しました: {str(e)}"
            )

        # 受信したデータが空でないか確認
        if len(audio_bytes) == 0:
            logger.error("音声データが空です")
            raise HTTPException(status_code=400, detail="音声データが空です")

        try:
            # 音声認識処理
            logger.debug("音声認識処理を開始します")
            responses = transcribe_streaming_v2(audio_bytes, language_codes=["ja-JP"])
            logger.debug("音声認識完了")
        except Exception as e:
            logger.error(f"音声認識エラー: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"音声認識エラー: {str(e)}")

        full_transcript: str = ""
        timed_transcription: List[Dict[str, str]] = []

        def format_time(time_obj: datetime.timedelta) -> str:
            seconds: float = time_obj.total_seconds()
            hrs: int = int(seconds // 3600)
            mins: int = int((seconds % 3600) // 60)
            secs: int = int(seconds % 60)
            msecs: int = int(seconds * 1000) % 1000
            return f"{hrs:02d}:{mins:02d}:{secs:02d}.{msecs:03d}"

        for response in responses:
            for result in response.results:
                alternative = result.alternatives[0]
                full_transcript += alternative.transcript + "\n"
                if alternative.words:
                    for w in alternative.words:
                        start_time_str: str = format_time(w.start_offset)
                        end_time_str: str = format_time(w.end_offset)
                        timed_transcription.append(
                            {
                                "start_time": start_time_str,
                                "end_time": end_time_str,
                                "text": w.word,
                            }
                        )
                else:
                    timed_transcription.append(
                        {
                            "start_time": "00:00:00",
                            "end_time": "00:00:00",
                            "text": alternative.transcript,
                        }
                    )

        logger.debug(
            f"文字起こし結果: {len(full_transcript)} 文字, {len(timed_transcription)} セグメント"
        )

        response_data: Dict[str, Any] = {
            "transcription": full_transcript.strip(),
            "timed_transcription": timed_transcription,
        }

        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=SPEECH2TEXT_LOG_MAX_LENGTH,
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"音声文字起こしエラー: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backend/generate-image")
async def generate_image_endpoint(
    request: Request,
    image_request: GenerateImageRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    request_info: Dict[str, Any] = await log_request(
        request, current_user, GENERATE_IMAGE_LOG_MAX_LENGTH
    )

    prompt: str = image_request.prompt
    model_name: str = image_request.model_name
    negative_prompt: Optional[str] = image_request.negative_prompt
    number_of_images: Optional[int] = image_request.number_of_images
    seed: Optional[int] = image_request.seed
    aspect_ratio: Optional[str] = image_request.aspect_ratio
    language: Optional[str] = image_request.language
    add_watermark: Optional[bool] = image_request.add_watermark
    safety_filter_level: Optional[str] = image_request.safety_filter_level
    person_generation: Optional[str] = image_request.person_generation

    kwargs: Dict[str, Any] = dict(
        prompt=prompt,
        model_name=model_name,
        negative_prompt=negative_prompt,
        seed=seed,
        number_of_images=number_of_images,
        aspect_ratio=aspect_ratio,
        language=language,
        add_watermark=add_watermark,
        safety_filter_level=safety_filter_level,
        person_generation=person_generation,
    )
    logger.debug(f"generate_image 関数の引数: {kwargs}")

    # 必須パラメータのチェック
    none_parameters: List[str] = [
        key for key, value in kwargs.items() if value is None and key != "seed"
    ]
    if none_parameters:
        return JSONResponse(
            status_code=400, content={"error": f"{none_parameters} is(are) required"}
        )

    try:
        image_list = generate_image(**kwargs)
        if not image_list:
            error_message: str = "画像生成に失敗しました。プロンプトにコンテンツポリシーに違反する内容（人物表現など）が含まれている可能性があります。別の内容を試してください。"
            logger.warning(error_message)
            raise HTTPException(status_code=500, detail=error_message)

        encode_images: List[str] = []
        for img_obj in image_list:
            img_base64: str = img_obj._as_base64_string()
            encode_images.append(img_base64)

        response_data: Dict[str, List[str]] = {"images": encode_images}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERATE_IMAGE_LOG_MAX_LENGTH,
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message: str = str(e)
        logger.error(f"画像生成エラー: {error_message}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)


@app.post("/backend/logout")
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


# 音声アップロード処理関数の変更部分
@app.post("/backend/whisper")
async def upload_audio(
    request: Request, 
    whisper_request: WhisperUploadRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:

    try:
        request_info: Dict[str, Any] = await log_request(
        request, current_user, GENERAL_LOG_MAX_LENGTH
        )


        # 認証情報の取得
        user_id: str = current_user["uid"]
        user_email: str = current_user.get("email", "")
        
        # middle_wareでフィルタリングされているので無いとは思うが念のためrequest_infoにX-Request-Idが設定されていることを確認する
        if "X-Request-Id" not in request_info:
            return JSONResponse(status_code=500, content={"detail": "X-Request-Idがリクエスト情報に含まれていません"})

        # Base64データのバリデーション
        if not whisper_request.audio_data:
            return JSONResponse(status_code=400, content={"detail": "音声データが提供されていません"})

        if not whisper_request.audio_data.startswith("data:"):
            return JSONResponse(status_code=400, content={"detail": "無効な音声データ形式です"})

        # MIMEタイプの取得
        mime_parts: List[str] = whisper_request.audio_data.split(";")[0].split(":")
        if len(mime_parts) < 2:
            return JSONResponse(status_code=400, content={"detail": "無効なMIMEタイプ形式"})

        mime_type: str = mime_parts[1]
        if not mime_type.startswith("audio/"):
            return JSONResponse(status_code=400, content={"detail": f"無効な音声フォーマット: {mime_type}"})

        # Base64データのデコード
        try:
            audio_content: bytes = base64.b64decode(whisper_request.audio_data.split(",")[1])
        except Exception:
            return JSONResponse(status_code=400, content={"detail": "Base64デコードに失敗しました"})

        # ファイルのハッシュ値を計算
        file_hash: str = hashlib.md5(audio_content).hexdigest()

        # MIMEタイプから拡張子を取得
        mime_mapping: Dict[str, str] = {
            "audio/wav": ".wav",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/webm": ".webm",
            "audio/aac": ".aac",
            "audio/m4a": ".m4a",
            "audio/x-m4a": ".m4a",
        }
        audio_file_extension: Optional[str] = mime_mapping.get(mime_type)
        if not audio_file_extension:
            return JSONResponse(status_code=400, content={"detail": f"サポートされていない音声フォーマット: {mime_type}"})
        # 音声ファイルのサイズを取得 (バイト単位)
        audio_size: int = len(audio_content)
        
        try:
            # メモリ上でファイルを処理
            audio_file = io.BytesIO(audio_content)
            
            # MIMEタイプに応じて適切な形式でロード
            if mime_type in ["audio/mp3", "audio/mpeg"]:
                audio = AudioSegment.from_mp3(audio_file)
            elif mime_type == "audio/wav":
                audio = AudioSegment.from_wav(audio_file)
            elif mime_type == "audio/ogg":
                audio = AudioSegment.from_ogg(audio_file)
            elif mime_type in ["audio/m4a", "audio/x-m4a"]:
                audio = AudioSegment.from_file(audio_file, format="m4a")
            elif mime_type == "audio/aac":
                audio = AudioSegment.from_file(audio_file, format="aac")
            elif mime_type == "audio/webm":
                audio = AudioSegment.from_file(audio_file, format="webm")
            else:
                # 未知の形式の場合はデフォルトで処理
                audio = AudioSegment.from_file(audio_file)
            
            # 長さをミリ秒単位で取得
            audio_duration = int(math.ceil(len(audio) / 1000))
            logger.debug(f"音声長さ: {audio_duration} 秒")
            
        except Exception as e:
            logger.error("音声長さの取得に失敗しました: %s", str(e))
            return JSONResponse(status_code=400, content={"detail": "音声長さの取得に失敗しました"})
        
        # GCSのパス設定
        storage_client: storage.Client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        base_dir: str = f"whisper/{user_id}/{file_hash}"
        
        
        # 音声ファイルのアップロード
        blob = bucket.blob(f"{base_dir}/origin{audio_file_extension}")
        blob.upload_from_string(audio_content, content_type=mime_type)

        # Firestoreにジョブ情報を記録
        # Firestoreにジョブ情報を記録
        db: firestore.Client = firestore.Client()
        # リクエストIDをそのままjob_idに使う。一意なので問題なし
        job_id: str = request_info['X-Request-Id']
        timestamp = firestore.SERVER_TIMESTAMP

        # 音声ファイルパスと文字起こしファイルパスを設定
        audio_file_path = f"{base_dir}/origin{audio_file_extension}"
        transcription_file_path = ""

        # ジョブデータの作成
        whisper_job: WhisperFirestoreData = WhisperFirestoreData(
            job_id=job_id,
            user_id=user_id,
            user_email=user_email,
            filename=whisper_request.filename,
            description=whisper_request.description,
            recording_date=whisper_request.recording_date,
            gcs_bucket_name=GCS_BUCKET_NAME,
            audio_file_path=audio_file_path,
            transcription_file_path=transcription_file_path,
            audio_duration=audio_duration,
            audio_size=audio_size,
            file_hash=file_hash,
            language=whisper_request.language or "ja",
            initial_prompt=whisper_request.initial_prompt or "",
            status="queued",
            created_at=timestamp,
            updated_at=timestamp,
            process_started_at=None,
            process_ended_at=None,
            tags=whisper_request.tags,
            error_message=None,
            # 話者数パラメータを追加
            num_speakers=whisper_request.num_speakers,
            min_speakers=whisper_request.min_speakers or 1,
            max_speakers=whisper_request.max_speakers or 1,
        )

        # Firestoreに保存
        db.collection(WHISPER_JOBS_COLLECTION).document(job_id).set(whisper_job.model_dump())

        # Pub/Subに通知
        publisher: pubsub_v1.PublisherClient = pubsub_v1.PublisherClient()
        topic_path: str = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC)

        # ISO 8601形式の現在時刻を生成
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

        message_data : WhisperPubSubMessageData= WhisperPubSubMessageData(
            job_id=job_id,
            event_type="new_job",
            timestamp=current_time
        )

        message_bytes: bytes = json.dumps(message_data).encode("utf-8")
        publish_future: pubsub_v1.publisher.futures.Future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()
        
        response_data = {"status": "success", "job_id": job_id, "file_hash": file_hash}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )

    except Exception as e:
        logger.exception("音声アップロードエラー")
        return JSONResponse(status_code=500, content={"detail": f"アップロードエラー: {str(e)}"})





# 静的ファイル配信設定
# 静的ファイルのマウント
app.mount(
    "/assets",
    StaticFiles(directory=os.path.join(FRONTEND_PATH, "assets")),
    name="assets",
)


@app.get("/vite.svg")
async def vite_svg() -> FileResponse:
    logger.debug("vite.svg リクエスト")
    svg_path: str = os.path.join(FRONTEND_PATH, "vite.svg")
    if os.path.isfile(svg_path):
        return FileResponse(svg_path, media_type="image/svg+xml")

    logger.warning(f"vite.svg が見つかりません。確認パス: {svg_path}")
    try:
        logger.debug(f"FRONTEND_PATH: {FRONTEND_PATH}")
        logger.debug(f"FRONTEND_PATH内のファイル一覧: {os.listdir(FRONTEND_PATH)}")
    except Exception as e:
        logger.error(f"FRONTEND_PATH内のファイル一覧取得エラー: {e}")

    raise HTTPException(status_code=404, detail="ファイルが見つかりません")


@app.get("/")
async def index() -> FileResponse:
    logger.debug("インデックスページリクエスト: %s", FRONTEND_PATH)
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))


@app.get("/{path:path}")
async def static_file(path: str) -> FileResponse:
    logger.debug(f"パスリクエスト: /{path}")
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))


# 以下テスト
def create_document(collection_name: str, document_id: str, data: Dict[str, Any]) -> str:
    doc_ref = firebase_db.collection(collection_name).document(document_id)
    doc_ref.set(data)
    return document_id


def get_document(collection_name: str, document_id: str) -> Optional[Dict[str, Any]]:
    doc_ref = firebase_db.collection(collection_name).document(document_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None


# %%
if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    # Hypercornの設定
    config: Config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    # config.loglevel = "info" if not DEBUG else "debug"
    # config.accesslog = "-"
    # config.errorlog = "-"
    config.loglevel = "info"
    config.workers = 1

    # SSL/TLS設定（証明書と秘密鍵のパスを指定）
    if (
        SSL_CERT_PATH
        and SSL_KEY_PATH
        and os.path.exists(SSL_CERT_PATH)
        and os.path.exists(SSL_KEY_PATH)
    ):
        config.certfile = SSL_CERT_PATH
        config.keyfile = SSL_KEY_PATH
        # SSLプロトコルを明示的に設定して安全性と互換性を確保
        config.ciphers = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20"
        logger.info("SSL/TLSが有効化されました")

        # HTTP/2を有効化し優先する
        config.alpn_protocols = ["h2", "http/1.1"]
        config.h2_max_concurrent_streams = 250  # HTTP/2の同時ストリーム数を設定
        config.h2_max_inbound_frame_size = 2**14  # HTTP/2フレームの最大サイズを設定
        logger.info("HTTP/2が有効化されました")
    else:
        logger.warning(
            "SSL/TLS証明書が見つからないか設定されていません。HTTP/1.1のみで動作します"
        )
        # HTTP/1.1のみを使用
        config.alpn_protocols = ["http/1.1"]

    logger.info(
        "Hypercornを使用してFastAPIアプリを起動します（TLS設定：%s） DEBUG: %s",
        "有効" if hasattr(config, "certfile") else "無効",
        bool(DEBUG),
    )

    # Hypercornでアプリを起動
    import asyncio

    asyncio.run(hypercorn.asyncio.serve(app, config))
