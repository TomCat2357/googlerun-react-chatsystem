# app.py
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
    Response,
    Body,
    File,
    UploadFile,
)
from utils.common import (
    logger,
    wrap_asyncgenerator_logger,
    create_dict_logger,
    generate_request_id,
    # limit_remote_addr,
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
    SPEECH_MAX_SECONDS,
    IMAGEN_MODELS,
    IMAGEN_NUMBER_OF_IMAGES,
    IMAGEN_ASPECT_RATIOS,
    IMAGEN_LANGUAGES,
    IMAGEN_ADD_WATERMARK,
    IMAGEN_SAFETY_FILTER_LEVELS,
    IMAGEN_PERSON_GENERATIONS,
    get_api_key_for_model,
)


from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Callable
from firebase_admin import auth, credentials
import firebase_admin
import os, json, asyncio, base64, time
from uuid import uuid4


from utils.geocoding_service import process_single_geocode, process_map_images
from utils.chat_utils import common_message_function
from utils.speech2text import transcribe_streaming_v2
from utils.generate_image import generate_image

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
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-Id"],
    expose_headers=["Authorization"],
)


# 認証ミドルウェア用の依存関係
async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("トークンが見つかりません")
        raise HTTPException(status_code=401, detail="認証が必要です")

    token = auth_header.split("Bearer ")[1]
    try:
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        return decoded_token
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))


# リクエストモデル
class GeocodeRequest(BaseModel):
    mode: str
    lines: List[str]
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


# 新しいRESTful APIエンドポイント - ジオコーディング
@app.post("/backend/geocoding")
async def geocoding_endpoint(
    request: GeocodeRequest, current_user: Dict = Depends(get_current_user)
):
    """
    ジオコーディングのための新しいRESTfulエンドポイント
    """
    mode = request.mode
    lines = request.lines
    options = request.options

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

    from utils.common import get_google_maps_api_key

    google_maps_api_key = get_google_maps_api_key()
    timestamp = int(time.time() * 1000)

    # StreamingResponseを使って結果を非同期的に返す
    async def generate_results():
        for idx, line in enumerate(lines):
            query = line.strip()
            if not query:
                continue

            # ジオコーディング処理
            result = await process_single_geocode(
                google_maps_api_key, mode, query, timestamp
            )

            # 結果をJSON形式で返す
            yield json.dumps(
                {
                    "type": "GEOCODE_RESULT",
                    "payload": {
                        "index": idx,
                        "result": result,
                        "progress": int(
                            (idx + 1) / len(lines) * 50
                        ),  # 50%までがジオコーディング処理
                    },
                }
            ) + "\n"

            # 画像取得処理（緯度経度が有効な場合のみ）
            show_satellite = options.get("showSatellite", False)
            show_street_view = options.get("showStreetView", False)

            if (
                (show_satellite or show_street_view)
                and result["latitude"] is not None
                and result["longitude"] is not None
            ):
                satellite_image, street_view_image = await process_map_images(
                    google_maps_api_key,
                    result["latitude"],
                    result["longitude"],
                    show_satellite,
                    show_street_view,
                    options.get("satelliteZoom", 18),
                    options.get("streetViewHeading"),
                    options.get("streetViewPitch", 0),
                    options.get("streetViewFov", 90),
                )

                # 画像結果を返す
                if satellite_image or street_view_image:
                    progress = 50 + int(
                        (idx + 1) / len(lines) * 50
                    )  # 残りの50%は画像処理
                    yield json.dumps(
                        {
                            "type": "IMAGE_RESULT",
                            "payload": {
                                "index": idx,
                                "satelliteImage": satellite_image,
                                "streetViewImage": street_view_image,
                                "progress": progress,
                            },
                        }
                    ) + "\n"

            # 処理間隔を空ける（レート制限対策）
            await asyncio.sleep(0.1)

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
        request_id = request.headers.get("X-Request-Id", generate_request_id())
        logger.debug("リクエストID: %s", request_id)

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
        return create_dict_logger(config_values, {"X-Request-Id": request_id})
    except Exception as e:
        logger.error("Config取得エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backend/verify-auth")
async def verify_auth(request: Request, current_user: Dict = Depends(get_current_user)):
    try:
        logger.debug("認証検証開始")
        logger.debug("トークンの復号化成功。ユーザー: %s", current_user.get("email"))
        request_id = request.headers.get("X-Request-Id", generate_request_id())
        logger.debug("リクエストID: %s", request_id)
        response_data = {
            "status": "success",
            "user": {
                "email": current_user.get("email"),
                "uid": current_user.get("uid"),
            },
            "expire_time": current_user.get("exp"),
        }
        logger.debug("認証検証完了")
        return create_dict_logger(response_data, {"X-Request-Id": request_id})
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
        request_id = request.headers.get("X-Request-Id", generate_request_id())
        logger.debug(f"リクエストID: {request_id}")

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
        @wrap_asyncgenerator_logger(meta_info={"X-Request-Id": request_id})
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
        request_id = request.headers.get("X-Request-Id", generate_request_id())
        logger.debug(f"リクエストID: {request_id}")

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
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"

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

        return create_dict_logger(response_data, {"X-Request-Id": request_id})
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"音声文字起こしエラー: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backend/generate-image")
async def generate_image_endpoint(
    request: Request,
    image_request: GenerateImageRequest, 
    current_user: Dict = Depends(get_current_user)
):
    request_id = request.headers.get("X-Request-Id", generate_request_id())
    logger.debug(f"リクエストID: {request_id}")
    
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
        return create_dict_logger(response_data, {'X-Request-Id': request_id})
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = str(e)
        logger.error(f"画像生成エラー: {error_message}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)


@app.post("/backend/logout")
async def logout(request: Request):
    try:
        request_id = request.headers.get("X-Request-Id", generate_request_id())
        logger.debug(f"リクエストID: {request_id}")
        logger.debug("ログアウト処理開始")
        
        response_data = {"status": "success", "message": "ログアウトに成功しました"}
        return create_dict_logger(response_data, {'X-Request-Id': request_id})
    except Exception as e:
        logger.error("ログアウト処理中にエラーが発生: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))


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


if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    # Hypercornの設定
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    config.loglevel = "info" if not DEBUG else "debug"
    config.accesslog = "-"
    config.errorlog = "-"
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
