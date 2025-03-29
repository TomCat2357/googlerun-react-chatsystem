### backend/app.py ###

# %% app.py
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
)
from utils.common import (
    logger,
    wrap_asyncgenerator_logger,
    create_dict_logger,
    sanitize_request_data,
    log_request,
    MAX_IMAGES,
    MAX_AUDIO_FILES,
    MAX_TEXT_FILES,
    MAX_LONG_EDGE,
    MAX_IMAGE_SIZE,
    FRONTEND_PATH,
    PORT,
    DEBUG,
    ORIGINS,
    SSL_CERT_PATH,
    SSL_KEY_PATH,
    MODELS,
    FIREBASE_CLIENT_SECRET_PATH,
    GOOGLE_MAPS_API_CACHE_TTL,
    GEOCODING_NO_IMAGE_MAX_BATCH_SIZE,
    GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE,
    GEOCODING_BATCH_SIZE,
    SPEECH_MAX_SECONDS,
    IMAGEN_MODELS,
    IMAGEN_NUMBER_OF_IMAGES,
    IMAGEN_ASPECT_RATIOS,
    IMAGEN_LANGUAGES,
    IMAGEN_ADD_WATERMARK,
    IMAGEN_SAFETY_FILTER_LEVELS,
    IMAGEN_PERSON_GENERATIONS,
    CONFIG_LOG_MAX_LENGTH,
    VERIFY_AUTH_LOG_MAX_LENGTH,
    SPEECH2TEXT_LOG_MAX_LENGTH,
    GENERATE_IMAGE_LOG_MAX_LENGTH,
    LOGOUT_LOG_MAX_LENGTH,
    CHAT_LOG_MAX_LENGTH,
    GEOCODING_LOG_MAX_LENGTH,
    MIDDLE_WARE_LOG_MAX_LENGTH,
    UNNEED_REQUEST_ID_PATH,
    UNNEED_REQUEST_ID_PATH_STARTSWITH,
    UNNEED_REQUEST_ID_PATH_ENDSWITH,
    SENSITIVE_KEYS,
    HF_AUTH_TOKEN,
    GCS_BUCKET_NAME,
    PUBSUB_TOPIC,
    EMAIL_NOTIFICATION,
    GCP_PROJECT_ID,
    GCP_REGION,
    BATCH_IMAGE_URL,
    get_api_key_for_model,
    get_current_user,
    GeocodeRequest,
    ChatRequest,
    SpeechToTextRequest,
    GenerateImageRequest,
    WhisperRequest,
    WhisperJobRequest,
)


from utils.geocoding_service import get_google_maps_api_key, process_optimized_geocode

from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Callable
from firebase_admin import auth, credentials, firestore
import firebase_admin
import os, json, asyncio, base64, time, re
import uuid
import datetime
from google.cloud import storage, pubsub_v1

from utils.chat_utils import common_message_function
from utils.speech2text import transcribe_streaming_v2
from utils.generate_image import generate_image
from functools import partial
from google.cloud import storage, batch_v1, firestore, tasks_v2
from google.protobuf.duration_pb2 import Duration

firebase_db = firestore.Client()

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
        cred = credentials.Certificate(FIREBASE_CLIENT_SECRET_PATH)
        firebase_admin.initialize_app(cred)  # 名前を指定しない
    else:
        logger.debug("Firebase認証情報なしで初期化")
        firebase_admin.initialize_app()  # 名前を指定しない


# FastAPIアプリケーションの初期化
app = FastAPI()

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
async def log_request_middleware(request: Request, call_next):
    # OPTIONSリクエストの場合はリクエストIDのチェックをスキップ
    # URLパスの取得
    path = request.url.path
    # OPTIONSリクエスト、静的アセット、viteのアイコンへのリクエストは処理をスキップ
    if request.method == "OPTIONS":
        return await call_next(request)

    # リクエストヘッダーからリクエストIDを取得
    request_id = request.headers.get("X-Request-Id", "")

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
    start_time = time.time()

    # リクエストの基本情報を収集してロギング
    # URLパスの取得
    path = request.url.path
    # HTTPメソッドの取得
    method = request.method
    # クライアントのIPアドレスを取得（取得できない場合は"unknown"）
    client_host = request.client.host if request.client else "unknown"
    # リクエストボディの取得とデコード
    body = await request.body()
    # ボディデータを指定された最大長に制限してデコード
    decoded_data = body.decode("utf-8")

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
    response = await call_next(request)

    # 処理時間の計算
    process_time = time.time() - start_time

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
    current_user: Dict = Depends(get_current_user),
):
    """
    ジオコーディングのための最適化されたRESTfulエンドポイント
    クライアントからキャッシュ情報を受け取り、
    最小限のAPI呼び出しで結果と画像を取得する
    """
    # リクエストの情報を取得
    request_info = await log_request(request, current_user, GEOCODING_LOG_MAX_LENGTH)
    logger.debug("リクエスト情報: %s", request_info)

    mode = geocoding_request.mode
    lines = geocoding_request.lines
    options = geocoding_request.options

    # 上限件数のチェック
    max_batch_size = (
        GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE
        if options.get("showSatellite") or options.get("showStreetView")
        else GEOCODING_NO_IMAGE_MAX_BATCH_SIZE
    )

    if len(lines) > max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"入力された件数は{len(lines)}件ですが、1回の送信で取得可能な上限は{max_batch_size}件です。",
        )

    google_maps_api_key = get_google_maps_api_key()
    timestamp = int(time.time() * 1000)

    # クエリの重複を排除し、元のインデックスを保持
    unique_queries = {}
    for idx, line_data in enumerate(lines):
        query = line_data.query
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
    async def generate_results():
        # 並行処理用のタスクリスト
        tasks = []

        # 重複排除したクエリごとにタスクを作成
        for query, query_info in unique_queries.items():
            line_data = query_info["data"]
            original_indices = query_info["indices"]

            # 処理タスクを作成
            task = process_optimized_geocode(
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
        chunk_size = GEOCODING_BATCH_SIZE
        total_chunks = (len(tasks) + chunk_size - 1) // chunk_size
        processed_chunks = 0

        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i : i + chunk_size]
            chunk_results = await asyncio.gather(*chunk)
            processed_chunks += 1

            # 進捗計算
            progress_base = int((processed_chunks / total_chunks) * 100)

            # 結果を順番に返す
            for result_chunks in chunk_results:
                for result_chunk in result_chunks:
                    # 進捗情報を埋め込み
                    try:
                        chunk_data = json.loads(result_chunk.rstrip())
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
async def get_config(request: Request, current_user: Dict = Depends(get_current_user)):
    try:

        request_info = await log_request(
            request, current_user, GEOCODING_LOG_MAX_LENGTH
        )
        logger.debug("リクエスト情報: %s", request_info)

        config_values = {
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
async def verify_auth(request: Request, current_user: Dict = Depends(get_current_user)):
    try:
        logger.debug("認証検証開始")
        logger.debug("トークンの復号化成功。ユーザー: %s", current_user.get("email"))
        request_info = await log_request(
            request, current_user, VERIFY_AUTH_LOG_MAX_LENGTH
        )

        response_data = {
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
    current_user: Dict = Depends(get_current_user),
):
    logger.debug("チャットリクエストを処理中")
    try:
        request_info = await log_request(request, current_user, CHAT_LOG_MAX_LENGTH)
        logger.debug("リクエスト情報: %s", request_info)

        messages = chat_request.messages
        model = chat_request.model
        logger.debug(f"モデル: {model}")

        if model is None:
            raise HTTPException(
                status_code=400, detail="モデル情報が提供されていません"
            )

        model_api_key = get_api_key_for_model(model)

        # メッセージ変換処理のログ出力を追加
        transformed_messages = []
        for msg in messages:
            # ユーザーメッセージに添付ファイルがある場合の処理
            if msg.get("role") == "user":
                # ファイルデータの処理とログ出力
                if "files" in msg and msg["files"]:
                    file_types = []
                    for file in msg["files"]:
                        mime_type = file.get("mimeType", "")
                        name = file.get("name", "")
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
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if isinstance(content, str):
                content_preview = content[:50] + "..." if len(content) > 50 else content
                logger.debug(f"メッセージ[{i}]: role={role}, content={content_preview}")
            elif isinstance(content, list):
                parts_info = []
                for part in content:
                    if part.get("type") == "text":
                        text = (
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
        async def generate_stream():
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
    current_user: Dict = Depends(get_current_user),
):
    logger.debug("音声認識処理開始")
    try:
        request_info = await log_request(
            request, current_user, VERIFY_AUTH_LOG_MAX_LENGTH
        )

        audio_data = speech_request.audio_data

        if not audio_data:
            logger.error("音声データが見つかりません")
            raise HTTPException(
                status_code=400, detail="音声データが提供されていません"
            )

        # ヘッダー除去（"data:audio/～;base64,..."形式の場合）
        if audio_data.startswith("data:"):
            _, audio_data = audio_data.split(",", 1)

        try:
            audio_bytes = base64.b64decode(audio_data)
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

        full_transcript = ""
        timed_transcription = []

        def format_time(time_obj):
            seconds = time_obj.total_seconds()
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            msecs = int(seconds * 1000) % 1000
            return f"{hrs:02d}:{mins:02d}:{secs:02d}.{msecs:03d}"

        for response in responses:
            for result in response.results:
                alternative = result.alternatives[0]
                full_transcript += alternative.transcript + "\n"
                if alternative.words:
                    for w in alternative.words:
                        start_time_str = format_time(w.start_offset)
                        end_time_str = format_time(w.end_offset)
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

        response_data = {
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
    current_user: Dict = Depends(get_current_user),
):
    request_info = await log_request(
        request, current_user, GENERATE_IMAGE_LOG_MAX_LENGTH
    )

    prompt = image_request.prompt
    model_name = image_request.model_name
    negative_prompt = image_request.negative_prompt
    number_of_images = image_request.number_of_images
    seed = image_request.seed
    aspect_ratio = image_request.aspect_ratio
    language = image_request.language
    add_watermark = image_request.add_watermark
    safety_filter_level = image_request.safety_filter_level
    person_generation = image_request.person_generation

    kwargs = dict(
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
    none_parameters = [
        key for key, value in kwargs.items() if value is None and key != "seed"
    ]
    if none_parameters:
        return JSONResponse(
            status_code=400, content={"error": f"{none_parameters} is(are) required"}
        )

    try:
        image_list = generate_image(**kwargs)
        if not image_list:
            error_message = "画像生成に失敗しました。プロンプトにコンテンツポリシーに違反する内容（人物表現など）が含まれている可能性があります。別の内容を試してください。"
            logger.warning(error_message)
            raise HTTPException(status_code=500, detail=error_message)

        encode_images = []
        for img_obj in image_list:
            img_base64 = img_obj._as_base64_string()
            encode_images.append(img_base64)

        response_data = {"images": encode_images}
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
        error_message = str(e)
        logger.error(f"画像生成エラー: {error_message}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)


@app.post("/backend/logout")
async def logout(request: Request):
    try:
        request_info = await log_request(request, None, LOGOUT_LOG_MAX_LENGTH)

        logger.debug("ログアウト処理開始")

        response_data = {"status": "success", "message": "ログアウトに成功しました"}
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
async def upload_audio(request: Request):
    try:
        # リクエストデータの取得
        data = await request.json()
        audio_data = data.get("audio_data")
        filename = data.get("filename")
        description = data.get("description", "")
        recording_date = data.get("recording_date", "")
        tags = data.get("tags", [])
        
        # 認証情報の取得
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_info = await verify_firebase_token(token)
        user_id = user_info["uid"]
        user_email = user_info.get("email", "")
        
        # Base64データの処理
        if not audio_data or not audio_data.startswith("data:"):
            return JSONResponse(status_code=400, content={"detail": "無効な音声データ形式です"})
            
        # ファイルのハッシュ値を計算
        import hashlib
        audio_content = base64.b64decode(audio_data.split(",")[1])
        file_hash = hashlib.md5(audio_content).hexdigest()
        
        # ファイル拡張子の取得
        mime_type = audio_data.split(";")[0].split(":")[1]
        extension = mime_mapping.get(mime_type, "mp3")
        
        # GCSのパス設定（新構造）
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        
        # 新しいパス構造: whisper/{user_id}/{file_hash}/origin.{ext}
        base_dir = f"whisper/{user_id}/{file_hash}"
        gcs_audio_path = f"{base_dir}/origin.{extension}"
        gcs_meta_path = f"{base_dir}/metadata.json"
        
        # 音声ファイルのアップロード
        blob = bucket.blob(gcs_audio_path)
        blob.upload_from_string(audio_content, content_type=mime_type)
        
        # Firestoreにジョブ情報を記録
        db = firestore.Client()
        job_id = str(uuid.uuid4())
        timestamp = firestore.SERVER_TIMESTAMP
        
        # 新しいメタデータ構造
        job_data = {
            "id": job_id,
            "user_id": user_id,
            "user_email": user_email,
            "filename": filename,
            "description": description or "",
            "recording_date": recording_date or "",
            "gcs_audio_path": f"gs://{GCS_BUCKET_NAME}/{gcs_audio_path}",
            "file_hash": file_hash,
            "status": "queued",
            "progress": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
            "process_started_at": None,
            "process_ended_at": None,
            "tags": tags,
            "error_message": None,
        }
        
        # Firestoreに保存
        db.collection("whisper_jobs").document(job_id).set(job_data)
        
        # GCSにメタデータも保存（デバッグ用）
        meta_blob = bucket.blob(gcs_meta_path)
        # SERVER_TIMESTAMPはJSON化できないのでNoneに一時変更
        json_job_data = job_data.copy()
        json_job_data["created_at"] = None
        json_job_data["updated_at"] = None
        meta_blob.upload_from_string(json.dumps(json_job_data), content_type="application/json")
        
        # Pub/Subに通知
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
        
        message_data = {
            "job_id": job_id,
            "user_id": user_id,
            "user_email": user_email,
            "file_hash": file_hash,
            "event_type": "new_job"
        }
        
        message_bytes = json.dumps(message_data).encode("utf-8")
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()
        
        return {"status": "success", "job_id": job_id, "file_hash": file_hash}
        
    except Exception as e:
        logger.exception("音声アップロードエラー")
        return JSONResponse(status_code=500, content={"detail": f"アップロードエラー: {str(e)}"})

# ジョブ一覧取得エンドポイント
@app.get("/backend/whisper/jobs")
async def list_jobs(request: Request):
    try:
        # 認証処理
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_info = await verify_firebase_token(token)
        user_id = user_info["uid"]
        
        # ユーザーのジョブ一覧を取得
        db = firestore.Client()
        jobs_query = db.collection("whisper_jobs").where("user_id", "==", user_id).order_by("created_at", direction=firestore.Query.DESCENDING)
        jobs = jobs_query.stream()
        
        job_list = []
        for job in jobs:
            job_data = job.to_dict()
            job_list.append({
                "id": job.id,
                "filename": job_data.get("filename"),
                "description": job_data.get("description", ""),
                "created_at": job_data.get("created_at"),
                "updated_at": job_data.get("updated_at"),
                "status": job_data.get("status"),
                "progress": job_data.get("progress", 0),
                "error_message": job_data.get("error_message"),
                "tags": job_data.get("tags", []),
                "file_hash": job_data.get("file_hash")
            })
        
        return {"jobs": job_list}
        
    except Exception as e:
        logger.exception("ジョブ一覧取得エラー")
        return JSONResponse(status_code=500, content={"detail": f"エラー: {str(e)}"})

# ジョブ情報取得エンドポイント（hashベースに変更）
@app.get("/backend/whisper/jobs/{hash}")
async def get_job_details(hash: str, request: Request):
    try:
        # 認証処理
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_info = await verify_firebase_token(token)
        user_id = user_info["uid"]
        
        # Firestoreからハッシュ値に基づくジョブを検索
        db = firestore.Client()
        jobs = db.collection("whisper_jobs").where("file_hash", "==", hash).where("user_id", "==", user_id).limit(1).get()
        
        job = next(jobs, None)
        if not job:
            return JSONResponse(status_code=404, content={"detail": "ジョブが見つかりません"})
        
        job_data = job.to_dict()
        job_id = job.id
        
        # 完了しているジョブの場合、文字起こし結果を取得
        if job_data.get("status") == "completed":
            storage_client = storage.Client()
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            
            # 新しいパス構造に基づく結果ファイルパス
            result_path = f"whisper/{user_id}/{hash}/transcription.json"
            blob = bucket.blob(result_path)
            
            if blob.exists():
                content = blob.download_as_text()
                segments = json.loads(content)
                
                # ストリーミング用の署名付きURLを生成
                audio_blob = bucket.blob(f"whisper/{user_id}/{hash}/origin.{job_data.get('filename', '').split('.')[-1]}")
                audio_url = audio_blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.timedelta(minutes=30),
                    method="GET"
                )
                
                return {
                    "id": job_id,
                    "filename": job_data.get("filename"),
                    "description": job_data.get("description"),
                    "recording_date": job_data.get("recording_date"),
                    "status": job_data.get("status"),
                    "gcs_audio_url": audio_url,
                    "segments": segments,
                    "file_hash": hash
                }
        
        # 完了していない場合は基本情報のみ返す
        return {
            "id": job_id,
            "filename": job_data.get("filename"),
            "description": job_data.get("description"),
            "status": job_data.get("status"),
            "progress": job_data.get("progress", 0),
            "error_message": job_data.get("error_message"),
            "file_hash": hash
        }
        
    except Exception as e:
        logger.exception("ジョブ詳細取得エラー")
        return JSONResponse(status_code=500, content={"detail": f"エラー: {str(e)}"})

@app.post("/backend/whisper/jobs/{job_id}/cancel")
async def cancel_whisper_job(
    request: Request,
    job_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """キュー内のジョブをキャンセルする（処理前のみ可能）"""
    request_info = await log_request(request, current_user, CHAT_LOG_MAX_LENGTH)
    logger.debug(f"Whisperジョブキャンセルリクエスト ({job_id}): %s", request_info)

    try:
        user_id = current_user.get("uid")

        # Firestoreからジョブデータを取得
        db = firestore.Client()
        job_ref = db.collection("whisper_jobs").document(job_id)
        job_doc = job_ref.get()

        if not job_doc.exists:
            raise HTTPException(
                status_code=404, detail=f"ジョブが見つかりません: {job_id}"
            )

        job_data = job_doc.to_dict()

        # 権限チェック
        if job_data.get("user_id") != user_id:
            raise HTTPException(
                status_code=403, detail="このジョブにアクセスする権限がありません"
            )

        # 状態チェック - pendingまたはqueuedのみキャンセル可能
        if job_data.get("status") not in ["pending", "queued"]:
            raise HTTPException(
                status_code=400,
                detail=f"このジョブは既に処理中または完了しているためキャンセルできません。現在のステータス: {job_data.get('status')}",
            )

        # Firestoreのジョブステータスを更新
        job_ref.update({"status": "canceled", "updated_at": firestore.SERVER_TIMESTAMP})

        # キャンセル通知をPub/Subに送信（オプション）
        if PUBSUB_TOPIC and not PUBSUB_TOPIC.startswith("projects/your-project"):
            try:
                publisher = pubsub_v1.PublisherClient()
                topic_path = PUBSUB_TOPIC

                message_data = {
                    "job_id": job_id,
                    "user_id": user_id,
                    "event_type": "cancel_job",
                }

                message_bytes = json.dumps(message_data).encode("utf-8")
                publish_future = publisher.publish(topic_path, data=message_bytes)
                publish_future.result()

                logger.debug(f"キャンセル通知をPub/Subに送信: {job_id}")
            except Exception as e:
                logger.warning(f"キャンセル通知の送信エラー（無視）: {str(e)}")

        return {
            "status": "success",
            "message": "ジョブがキャンセルされました",
            "job_id": job_id,
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Whisperジョブキャンセルエラー: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backend/whisper/jobs/queue")
async def get_whisper_queue(
    request: Request,
    current_user: Dict = Depends(get_current_user),
):
    """キュー内のジョブ一覧を取得する（管理者用）"""
    request_info = await log_request(request, current_user, CHAT_LOG_MAX_LENGTH)
    logger.debug("Whisperキュー一覧取得: %s", request_info)

    try:
        user_id = current_user.get("uid")
        user_email = current_user.get("email")

        # 管理者権限チェック（メールドメインや特定のユーザーIDでチェックするなど）
        # 例: 特定のドメインを持つメールアドレスのみ管理者とする
        admin_domains = os.environ.get("ADMIN_EMAIL_DOMAINS", "yourdomain.com").split(
            ","
        )
        is_admin = any(user_email.endswith(f"@{domain}") for domain in admin_domains)

        if not is_admin:
            raise HTTPException(status_code=403, detail="管理者権限がありません")

        # Firestoreからキュー内のジョブを取得
        db = firestore.Client()
        jobs_query = db.collection("whisper_jobs").where(
            "status", "in", ["pending", "queued", "processing"]
        )
        jobs_docs = jobs_query.stream()

        jobs_list = []
        for doc in jobs_docs:
            job_data = doc.to_dict()
            jobs_list.append(
                {
                    "id": doc.id,
                    "user_id": job_data.get("user_id"),
                    "user_email": job_data.get("user_email"),
                    "filename": job_data.get("filename"),
                    "status": job_data.get("status"),
                    "created_at": job_data.get("created_at"),
                    "updated_at": job_data.get("updated_at"),
                }
            )

        # 作成日時でソート（新しい順）
        jobs_list.sort(key=lambda x: x.get("created_at", 0), reverse=True)

        return {"status": "success", "jobs": jobs_list}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Whisperキュー取得エラー: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backend/whisper/jobs/{job_id}/edit")
async def update_whisper_transcript(
    request: Request,
    job_id: str,
    edit_request: WhisperJobRequest,
    current_user: Dict = Depends(get_current_user),
):
    """文字起こし編集内容をGCSとFirestoreに保存する"""
    request_info = await log_request(request, current_user, CHAT_LOG_MAX_LENGTH)
    logger.debug(f"Whisper編集リクエスト ({job_id}): %s", request_info)

    try:
        user_id = current_user.get("uid")

        # Firestoreからメタデータを取得
        db = firestore.Client()
        job_ref = db.collection("whisper_jobs").document(job_id)
        job_doc = job_ref.get()

        if not job_doc.exists:
            raise HTTPException(
                status_code=404, detail=f"ジョブが見つかりません: {job_id}"
            )

        # メタデータを読み込む
        job_data = job_doc.to_dict()

        # 権限チェック
        if job_data.get("user_id") != user_id:
            raise HTTPException(
                status_code=403, detail="このジョブにアクセスする権限がありません"
            )

        # ステータスチェック
        if job_data.get("status") != "completed":
            # GCSで結果ファイルを確認
            storage_client = storage.Client()
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            transcription_path = f"whisper/{user_id}/{job_id}/transcription.json"
            transcription_blob = bucket.blob(transcription_path)

            if not transcription_blob.exists():
                raise HTTPException(
                    status_code=400,
                    detail="このジョブはまだ完了していないか、結果ファイルがありません",
                )

            # 結果があるのに状態が完了でない場合、状態を更新
            job_ref.update(
                {"status": "completed", "updated_at": firestore.SERVER_TIMESTAMP}
            )

        # 編集データの検証
        segments = edit_request.segments
        if not segments:
            raise HTTPException(
                status_code=400, detail="編集データが提供されていません"
            )

        # GCSに編集結果を保存
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)

        # 編集結果ファイルをアップロード
        edited_path = f"whisper/{user_id}/{job_id}/transcription_edited.json"
        edited_blob = bucket.blob(edited_path)
        edited_blob.upload_from_string(
            json.dumps(segments, ensure_ascii=False, indent=2),
            content_type="application/json",
        )

        # 最新の編集済みファイルを通常の結果ファイルとして上書き保存
        transcription_path = f"whisper/{user_id}/{job_id}/transcription.json"
        transcription_blob = bucket.blob(transcription_path)
        transcription_blob.upload_from_string(
            json.dumps(segments, ensure_ascii=False, indent=2),
            content_type="application/json",
        )

        # Firestoreのメタデータを更新
        job_ref.update(
            {
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_edited_at": firestore.SERVER_TIMESTAMP,
            }
        )

        return {"status": "success", "message": "編集内容が保存されました"}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Whisper編集保存エラー: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# 静的ファイル配信設定
# 静的ファイルのマウント
app.mount(
    "/assets",
    StaticFiles(directory=os.path.join(FRONTEND_PATH, "assets")),
    name="assets",
)


@app.get("/vite.svg")
async def vite_svg():
    logger.debug("vite.svg リクエスト")
    svg_path = os.path.join(FRONTEND_PATH, "vite.svg")
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
async def index():
    logger.debug("インデックスページリクエスト: %s", FRONTEND_PATH)
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))


@app.get("/{path:path}")
async def static_file(path: str):
    logger.debug(f"パスリクエスト: /{path}")
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))


# 以下テスト
def create_document(collection_name, document_id, data):
    doc_ref = firebase_db.collection(collection_name).document(document_id)
    doc_ref.set(data)
    return document_id


def get_document(collection_name, document_id):
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
    config = Config()
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


### End of file: backend/app.py ###
