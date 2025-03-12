
### backend/app.py ###

# app.py
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
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
    process_uploaded_image,
    limit_remote_addr,
    verify_firebase_token,
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
    CHUNK_STORE,
    GOOGLE_MAPS_API_CACHE_TTL,
    GEOCODING_NO_IMAGE_MAX_BATCH_SIZE,
    GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE,
    SPEECH_MAX_SECONDS,
    MAX_PAYLOAD_SIZE,
    IMAGEN_MODELS,
    IMAGEN_NUMBER_OF_IMAGES,
    IMAGEN_ASPECT_RATIOS,
    IMAGEN_LANGUAGES,
    IMAGEN_ADD_WATERMARK,
    IMAGEN_SAFETY_FILTER_LEVELS,
    IMAGEN_PERSON_GENERATIONS,
    get_api_key_for_model,
)

# 新規追加
from utils.file_utils import (
    process_uploaded_image,
    process_audio_file,
    process_text_file,
    prepare_message_for_ai,
    parse_csv_preview,
    process_docx_text,
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


from utils.websocket_manager import (
    ConnectionManager,
    WebSocketMessageType,
    verify_token,
)
from utils.geocoding_service import process_geocoding, process_single_geocode, process_map_images
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

# 接続マネージャのインスタンス作成
manager = ConnectionManager()

logger.debug("ORIGINS: %s", ORIGINS)

# FastAPIのCORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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


# IPガードミドルウェア
@app.middleware("http")
async def ip_guard(request: Request, call_next):
    try:
        limit_remote_addr(request)
        response = await call_next(request)
        logger.info('レスポンスタイプ: %s', str(type(response)))
        logger.info('レスポンス: %s', str(response))
        return response
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# リクエストモデル
class GeocodeRequest(BaseModel):
    mode: str
    lines: List[str]
    options: Dict[str, Any]


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    model: str
    chunked: Optional[bool] = False
    chunkId: Optional[str] = None
    chunkIndex: Optional[int] = None
    totalChunks: Optional[int] = None
    chunkData: Optional[str] = None


class SpeechToTextRequest(BaseModel):
    audio_data: str
    chunked: Optional[bool] = False
    chunkId: Optional[str] = None
    chunkIndex: Optional[int] = None
    totalChunks: Optional[int] = None
    chunkData: Optional[str] = None


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


# WebSocketエンドポイント
@app.websocket("/ws/geocoding")
async def websocket_geocoding(websocket: WebSocket):
    logger.debug("WebSocket接続リクエスト受信")
    await websocket.accept()

    client_id = f"client_{id(websocket)}"
    logger.debug(f"WebSocketクライアントID割り当て: {client_id}")

    try:
        # 接続の確立
        await manager.connect(websocket, client_id)
        logger.debug(f"クライアント {client_id} が接続しました")
        # 認証処理を復活させる
        logger.debug("WebSocket認証処理開始")
        decoded_token = await verify_token(websocket)
        if not decoded_token:
            logger.error("WebSocket認証失敗")
            await manager.send_error(client_id, "認証に失敗しました")
            return

        logger.debug(f"WebSocket認証成功: {decoded_token.get('email')}")

        # メッセージの処理
        while True:
            logger.debug("WebSocketメッセージ待機中")
            data = await websocket.receive_json()
            logger.debug(f"WebSocketメッセージ受信: {data.get('type', 'unknown')}")

            if data.get("type") == WebSocketMessageType.GEOCODE_REQUEST:
                payload = data.get("payload", {})
                mode = payload.get("mode", "address")
                lines = payload.get("lines", [])
                options = payload.get("options", {})

                # 上限件数のチェック
                max_batch_size = (
                    GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE
                    if options.get("showSatellite") or options.get("showStreetView")
                    else GEOCODING_NO_IMAGE_MAX_BATCH_SIZE
                )

                if len(lines) > max_batch_size:
                    await manager.send_error(
                        client_id,
                        f"入力された件数は{len(lines)}件ですが、1回の送信で取得可能な上限は{max_batch_size}件です。",
                    )
                    continue

                # 本番の非同期処理を実行
                asyncio.create_task(
                    process_geocoding(
                        manager,
                        client_id=client_id,
                        mode=mode,
                        lines=lines,
                        options=options,
                    )
                )
    except WebSocketDisconnect:
        logger.debug(f"クライアント切断: {client_id}")
    except Exception as e:
        logger.error(f"WebSocketエラー: {str(e)}", exc_info=True)
    finally:
        try:
            manager.disconnect(client_id)
            logger.debug(f"クライアント {client_id} との接続を解除しました")
        except Exception as e:
            logger.error(f"接続解除エラー: {str(e)}")


# 新しいRESTful APIエンドポイント - ジオコーディング
@app.post("/backend/geocoding")
async def geocoding_endpoint(
    request: GeocodeRequest,
    current_user: Dict = Depends(get_current_user)
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
            detail=f"入力された件数は{len(lines)}件ですが、1回の送信で取得可能な上限は{max_batch_size}件です。"
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
                google_maps_api_key, 
                mode, 
                query, 
                timestamp
            )
            
            # 結果をJSON形式で返す
            yield json.dumps({
                "type": "GEOCODE_RESULT",
                "payload": {
                    "index": idx,
                    "result": result,
                    "progress": int((idx + 1) / len(lines) * 50)  # 50%までがジオコーディング処理
                }
            }) + "\n"
            
            # 画像取得処理（緯度経度が有効な場合のみ）
            show_satellite = options.get("showSatellite", False)
            show_street_view = options.get("showStreetView", False)
            
            if (show_satellite or show_street_view) and result["latitude"] is not None and result["longitude"] is not None:
                satellite_image, street_view_image = await process_map_images(
                    google_maps_api_key,
                    result["latitude"],
                    result["longitude"],
                    show_satellite,
                    show_street_view,
                    options.get("satelliteZoom", 18),
                    options.get("streetViewHeading"),
                    options.get("streetViewPitch", 0),
                    options.get("streetViewFov", 90)
                )
                
                # 画像結果を返す
                if satellite_image or street_view_image:
                    progress = 50 + int((idx + 1) / len(lines) * 50)  # 残りの50%は画像処理
                    yield json.dumps({
                        "type": "IMAGE_RESULT",
                        "payload": {
                            "index": idx,
                            "satelliteImage": satellite_image,
                            "streetViewImage": street_view_image,
                            "progress": progress
                        }
                    }) + "\n"
            
            # 処理間隔を空ける（レート制限対策）
            await asyncio.sleep(0.1)
        
        # 全ての処理が完了したことを通知
        yield json.dumps({
            "type": "COMPLETE",
            "payload": {}
        }) + "\n"
    
    return StreamingResponse(
        generate_results(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Transfer-Encoding": "chunked"}
    )


# テスト用のWebSocketエンドポイント
@app.websocket("/ws/echo")
async def websocket_echo(websocket: WebSocket):
    logger.debug("Echoテスト: WebSocket接続リクエスト受信")
    await websocket.accept()
    logger.debug("Echoテスト: WebSocket接続確立")
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Echoテスト: メッセージ受信: {data}")
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        logger.debug("Echoテスト: クライアント切断")
    except Exception as e:
        logger.error(f"Echoテスト: エラー: {str(e)}", exc_info=True)


@app.get("/backend/config")
async def get_config(current_user: Dict = Depends(get_current_user)):
    try:
        config_values = {
            "MAX_IMAGES": MAX_IMAGES,
            "MAX_AUDIO_FILES": MAX_AUDIO_FILES,
            "MAX_TEXT_FILES": MAX_TEXT_FILES,
            "MAX_LONG_EDGE": MAX_LONG_EDGE,
            "MAX_IMAGE_SIZE": MAX_IMAGE_SIZE,
            "MAX_PAYLOAD_SIZE": MAX_PAYLOAD_SIZE,
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
        return config_values
    except Exception as e:
        logger.error("Config取得エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backend/verify-auth")
async def verify_auth(current_user: Dict = Depends(get_current_user)):
    try:
        logger.debug("認証検証開始")
        logger.debug("トークンの復号化成功。ユーザー: %s", current_user.get("email"))
        response_data = {
            "status": "success",
            "user": {
                "email": current_user.get("email"),
                "uid": current_user.get("uid"),
            },
            "expire_time": current_user.get("exp"),
        }
        logger.debug("認証検証完了")
        return response_data
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))


# チャンクデータ処理関数を修正
async def process_chunked_data(data: Dict[str, Any]):
    chunk_id = data.get("chunkId")
    chunk_index = data.get("chunkIndex")
    total_chunks = data.get("totalChunks")
    chunk_data_b64 = data.get("chunkData")
    is_binary = data.get("isBinary", False)  # バイナリデータかどうかのフラグ

    if not chunk_id or chunk_index is None or not total_chunks or not chunk_data_b64:
        logger.error(
            "チャンク情報が不足しています: %s",
            {
                k: v is None
                for k, v in {
                    "chunkId": chunk_id,
                    "chunkIndex": chunk_index,
                    "totalChunks": total_chunks,
                    "chunkData": chunk_data_b64,
                }.items()
            },
        )
        raise HTTPException(status_code=400, detail="チャンク情報が不足しています")

    # チャンク数が多すぎる場合はエラー
    if total_chunks > 20000:
        logger.error("チャンク数が多すぎます: %s", total_chunks)
        raise HTTPException(
            status_code=400,
            detail=f"チャンク数が多すぎます（{total_chunks}）。ファイルを小さくしてください。",
        )

    try:
        # base64デコードしてバイナリ取得
        try:
            # チャンクデータを小さく処理
            chunk_data = base64.b64decode(chunk_data_b64)
        except Exception as e:
            logger.error("Base64デコードエラー: %s", str(e))
            raise HTTPException(status_code=400, detail=f"不正なBase64データ: {str(e)}")

        # チャンク情報のログ出力
        logger.debug(
            "チャンク受信: %s - インデックス %d/%d (サイズ: %.2f KB)",
            chunk_id,
            chunk_index,
            total_chunks,
            len(chunk_data) / 1024,
        )

        # チャンクストアの初期化
        if chunk_id not in CHUNK_STORE:
            CHUNK_STORE[chunk_id] = {
                "chunks": {},
                "is_binary": is_binary,
                "timestamp": time.time(),
            }

        # チャンクを保存
        CHUNK_STORE[chunk_id]["chunks"][chunk_index] = chunk_data

        # ストアのクリーンアップ（古いチャンクを削除）
        current_time = time.time()
        expired_chunk_ids = []
        for c_id, c_data in CHUNK_STORE.items():
            if (
                c_id != chunk_id and current_time - c_data.get("timestamp", 0) > 3600
            ):  # 1時間以上経過したチャンク
                expired_chunk_ids.append(c_id)

        for expired_id in expired_chunk_ids:
            del CHUNK_STORE[expired_id]
            logger.debug("期限切れチャンクを削除: %s", expired_id)

        # 全チャンク受信チェック
        received_count = len(CHUNK_STORE[chunk_id]["chunks"])

        if received_count < total_chunks:
            return {
                "status": "chunk_received",
                "chunkId": chunk_id,
                "received": received_count,
                "total": total_chunks,
            }

        # 全チャンク受信済みの場合、順次再構築
        try:
            logger.debug("全チャンク受信完了。データ組み立て開始: %s", chunk_id)

            # チャンクを順番通りに結合
            assembled_bytes = b""
            try:
                for i in range(total_chunks):
                    if i not in CHUNK_STORE[chunk_id]["chunks"]:
                        logger.error("チャンクが欠落しています: インデックス %d", i)
                        raise HTTPException(
                            status_code=500, detail=f"チャンク {i} が欠落しています"
                        )
                    assembled_bytes += CHUNK_STORE[chunk_id]["chunks"][i]
            except Exception as e:
                logger.error("チャンク結合エラー: %s", str(e))
                raise HTTPException(
                    status_code=500, detail=f"チャンク結合エラー: {str(e)}"
                )

            # チャンクストアをクリア
            is_binary = CHUNK_STORE[chunk_id]["is_binary"]
            del CHUNK_STORE[chunk_id]

            # バイナリデータの場合は変換せずに返す
            if is_binary:
                logger.debug(
                    "バイナリデータ組み立て完了: %.2f KB", len(assembled_bytes) / 1024
                )
                return {"binary_data": assembled_bytes}

            # テキストデータの場合はUTF-8としてデコードしJSONとしてパース
            try:
                assembled_str = assembled_bytes.decode("utf-8")
                parsed_json = json.loads(assembled_str)
                logger.debug("JSONデータ組み立て完了")
                return parsed_json
            except UnicodeDecodeError as e:
                logger.error("UTF-8デコードエラー: %s", str(e))
                raise HTTPException(
                    status_code=500, detail=f"UTF-8デコードエラー: {str(e)}"
                )
            except json.JSONDecodeError as e:
                logger.error("JSONパースエラー: %s", str(e))
                raise HTTPException(
                    status_code=500, detail=f"JSONパースエラー: {str(e)}"
                )
        except Exception as e:
            logger.error("チャンクデータの再構築エラー: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"チャンクデータの処理エラー: {str(e)}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("チャンク処理中の予期せぬエラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"チャンク処理エラー: {str(e)}")


@app.post("/backend/chat")
async def chat(request: Request, current_user: Dict = Depends(get_current_user)):
    logger.debug("チャットリクエストを処理中")
    try:
        # リクエストボディの読み込み
        body = await request.json()

        # チャンク処理の確認
        if body.get("chunked"):
            logger.debug("チャンクされたデータです")
            try:
                # チャンクデータの処理
                data = await process_chunked_data(body)

                # 追加: 中間チャンクレスポンスの場合はそのまま返す
                if data.get("status") == "chunk_received":
                    logger.debug(
                        f"中間チャンク処理: {data.get('received')}/{data.get('total')}"
                    )
                    return data

            except Exception as e:
                logger.error("チャンク組み立てエラー: %s", str(e), exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
        else:
            logger.debug("チャンクされていないデータです")
            data = body

        messages = data.get("messages", [])
        model = data.get("model")
        logger.debug(f"モデル: {model}")

        if model is None:
            raise HTTPException(
                status_code=400, detail="モデル情報が提供されていません"
            )

        model_api_key = get_api_key_for_model(model)
        error_keyword = "@trigger_error"
        error_flag = False

        for msg in messages:
            content = msg.get("content", "")
            if error_keyword == content:
                error_flag = True
                break

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
                        text = part.get("text", "")[:20] + "..." if len(part.get("text", "")) > 20 else part.get("text", "")
                        parts_info.append(f"text: {text}")
                    elif part.get("type") == "image_url":
                        parts_info.append("image")
                logger.debug(f"メッセージ[{i}]: role={role}, parts={parts_info}")
        
        if error_flag:
            raise HTTPException(
                status_code=500, detail="意図的なエラーがトリガーされました"
            )

        # ストリーミングレスポンスの作成
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
async def speech2text(request: Request, current_user: Dict = Depends(get_current_user)):
    logger.debug("音声認識処理開始")
    try:
        # リクエストボディの読み込み
        body = await request.json()

        # チャンク処理の確認
        if body.get("chunked"):
            logger.debug("チャンクされたデータです")
            try:
                # チャンクデータの処理（isBinaryフラグを追加）
                body["isBinary"] = True  # 音声データはバイナリとして処理
                data = await process_chunked_data(body)

                # 中間ステータスのチェック - これが重要な修正部分
                if data.get("status") == "chunk_received":
                    # 中間チャンクの場合は、そのままステータスを返す
                    logger.debug(
                        f"チャンク中間状態: {data.get('received')}/{data.get('total')} 受信済み"
                    )
                    return data

                # バイナリデータが返された場合の処理
                if "binary_data" in data:
                    audio_bytes = data["binary_data"]
                    logger.debug(
                        f"バイナリデータ受信完了: {len(audio_bytes) / 1024:.2f} KB"
                    )
                    audio_data_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    data = {"audio_data": audio_data_b64}
                else:
                    logger.error(f"予期しないデータ形式: {data.keys()}")
                    raise HTTPException(status_code=400, detail="不正なデータ形式")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"チャンク組み立てエラー: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
        else:
            logger.debug("チャンクされていないデータです")
            data = body

        audio_data = data.get("audio_data", "")
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
        return {
            "transcription": full_transcript.strip(),
            "timed_transcription": timed_transcription,
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"音声文字起こしエラー: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backend/generate-image")
async def generate_image_endpoint(
    request: GenerateImageRequest, current_user: Dict = Depends(get_current_user)
):
    prompt = request.prompt
    model_name = request.model_name
    negative_prompt = request.negative_prompt
    number_of_images = request.number_of_images
    seed = request.seed
    aspect_ratio = request.aspect_ratio
    language = request.language
    add_watermark = request.add_watermark
    safety_filter_level = request.safety_filter_level
    person_generation = request.person_generation

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
        return {"images": encode_images}
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = str(e)
        logger.error(f"画像生成エラー: {error_message}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)


@app.post("/backend/logout")
async def logout():
    try:
        logger.debug("ログアウト処理開始")
        return {"status": "success", "message": "ログアウトに成功しました"}
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
    config.accesslog = '-'
    config.errorlog = '-'
    config.workers = 1
    
    # SSL/TLS設定（証明書と秘密鍵のパスを指定）
    if SSL_CERT_PATH and SSL_KEY_PATH and os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
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
        logger.warning("SSL/TLS証明書が見つからないか設定されていません。HTTP/1.1のみで動作します")
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


### backend/utils/geocoding_service.py ###

# utils/geocoding_service.py
import base64
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from utils.common import (
    logger, 
    get_google_maps_api_key
)
from utils.maps import get_coordinates, get_address, get_static_map, get_street_view
from utils.websocket_manager import ConnectionManager


async def process_geocoding(
    manager: ConnectionManager,
    client_id: str,
    mode: str,
    lines: List[str],
    options: Dict[str, Any]
):
    """
    ジオコーディング処理のメイン関数（WebSocket用）
    """
    google_maps_api_key = get_google_maps_api_key()
    timestamp = int(time.time() * 1000)
    total_lines = len(lines)
    
    # 画像オプションの取得
    show_satellite = options.get("showSatellite", False)
    show_street_view = options.get("showStreetView", False)
    satellite_zoom = options.get("satelliteZoom", 18)
    street_view_heading = options.get("streetViewHeading")
    street_view_pitch = options.get("streetViewPitch", 0)
    street_view_fov = options.get("streetViewFov", 90)
    
    try:
        for idx, line in enumerate(lines):
            query = line.strip()
            if not query:
                continue
            
            # ジオコーディング処理
            result = await process_single_geocode(
                google_maps_api_key, 
                mode, 
                query, 
                timestamp
            )
            
            # ジオコーディング結果をクライアントに送信
            progress = int((idx + 1) / total_lines * 50)  # 50%までがジオコーディング処理
            await manager.send_geocode_result(client_id, idx, result, progress)
            
            # 画像取得処理（緯度経度が有効な場合のみ）
            if (show_satellite or show_street_view) and result["latitude"] is not None and result["longitude"] is not None:
                satellite_image, street_view_image = await process_map_images(
                    google_maps_api_key,
                    result["latitude"],
                    result["longitude"],
                    show_satellite,
                    show_street_view,
                    satellite_zoom,
                    street_view_heading,
                    street_view_pitch,
                    street_view_fov
                )
                
                # 画像結果をクライアントに送信
                if satellite_image or street_view_image:
                    progress = 50 + int((idx + 1) / total_lines * 50)  # 残りの50%は画像処理
                    await manager.send_image_result(
                        client_id, 
                        idx, 
                        satellite_image, 
                        street_view_image, 
                        progress
                    )
            
            # 処理間隔を空ける（レート制限対策）
            await asyncio.sleep(0.1)
        
        # 全ての処理が完了したことを通知
        await manager.send_complete(client_id)
        
    except Exception as e:
        logger.error(f"ジオコーディング処理エラー: {str(e)}", exc_info=True)
        await manager.send_error(client_id, f"処理エラー: {str(e)}")


async def process_single_geocode(
    api_key: str, 
    mode: str, 
    query: str, 
    timestamp: int
) -> Dict[str, Any]:
    """単一のジオコーディングリクエストを処理する"""
    if mode == "address":
        # 住所→緯度経度の変換
        geocode_data = get_coordinates(api_key, query)
        
        if geocode_data.get("status") == "OK" and geocode_data.get("results"):
            result_data = geocode_data["results"][0]
            location = result_data["geometry"]["location"]
            return {
                "query": query,
                "status": geocode_data.get("status"),
                "formatted_address": result_data.get("formatted_address", ""),
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
                "location_type": result_data["geometry"].get("location_type", ""),
                "place_id": result_data.get("place_id", ""),
                "types": ", ".join(result_data.get("types", [])),
                "error": "",
                "isCached": False,
                "fetchedAt": timestamp,
                "mode": "address"
            }
        else:
            return {
                "query": query,
                "status": geocode_data.get("status", "エラー"),
                "formatted_address": "",
                "latitude": None,
                "longitude": None,
                "location_type": "",
                "place_id": "",
                "types": "",
                "error": geocode_data.get("status", "エラー"),
                "isCached": False,
                "fetchedAt": timestamp,
                "mode": "address"
            }
    else:
        # 緯度経度→住所の変換
        parts = query.replace(" ", "").split(",")
        
        if len(parts) != 2:
            return {
                "query": query,
                "status": "INVALID_FORMAT",
                "formatted_address": "",
                "latitude": None,
                "longitude": None,
                "location_type": "",
                "place_id": "",
                "types": "",
                "error": "無効な形式",
                "isCached": False,
                "fetchedAt": timestamp,
                "mode": "latlng"
            }
        else:
            try:
                lat = float(parts[0])
                lng = float(parts[1])
                
                if lat < -90 or lat > 90 or lng < -180 or lng > 180:
                    return {
                        "query": query,
                        "status": "INVALID_RANGE",
                        "formatted_address": "",
                        "latitude": lat,
                        "longitude": lng,
                        "location_type": "",
                        "place_id": "",
                        "types": "",
                        "error": "範囲外",
                        "isCached": False,
                        "fetchedAt": timestamp,
                        "mode": "latlng"
                    }
                else:
                    geocode_data = get_address(api_key, lat, lng)
                    
                    if geocode_data.get("status") == "OK" and geocode_data.get("results"):
                        result_data = geocode_data["results"][0]
                        location = result_data["geometry"]["location"]
                        return {
                            "query": query,
                            "status": geocode_data.get("status"),
                            "formatted_address": result_data.get("formatted_address", ""),
                            "latitude": location.get("lat"),
                            "longitude": location.get("lng"),
                            "location_type": result_data["geometry"].get("location_type", ""),
                            "place_id": result_data.get("place_id", ""),
                            "types": ", ".join(result_data.get("types", [])),
                            "error": "",
                            "isCached": False,
                            "fetchedAt": timestamp,
                            "mode": "latlng"
                        }
                    else:
                        return {
                            "query": query,
                            "status": geocode_data.get("status", "エラー"),
                            "formatted_address": "",
                            "latitude": lat,
                            "longitude": lng,
                            "location_type": "",
                            "place_id": "",
                            "types": "",
                            "error": geocode_data.get("status", "エラー"),
                            "isCached": False,
                            "fetchedAt": timestamp,
                            "mode": "latlng"
                        }
            except ValueError:
                return {
                    "query": query,
                    "status": "INVALID_FORMAT",
                    "formatted_address": "",
                    "latitude": None,
                    "longitude": None,
                    "location_type": "",
                    "place_id": "",
                    "types": "",
                    "error": "数値変換エラー",
                    "isCached": False,
                    "fetchedAt": timestamp,
                    "mode": "latlng"
                }


async def process_map_images(
    api_key: str,
    latitude: float,
    longitude: float,
    show_satellite: bool,
    show_street_view: bool,
    satellite_zoom: int,
    street_view_heading: Optional[float],
    street_view_pitch: float,
    street_view_fov: float
) -> Tuple[Optional[str], Optional[str]]:
    """地図画像を取得する処理"""
    satellite_image = None
    street_view_image = None
    
    # 衛星画像の取得
    if show_satellite:
        try:
            response = get_static_map(
                api_key,
                latitude,
                longitude,
                zoom=satellite_zoom,
                size=(600, 600),
                map_type="satellite"
            )
            
            if response.ok:
                img_base64 = base64.b64encode(response.content).decode('utf-8')
                satellite_image = f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            logger.error(f"衛星画像取得エラー: {str(e)}")
    
    # ストリートビュー画像の取得
    if show_street_view:
        try:
            response = get_street_view(
                api_key,
                latitude,
                longitude,
                size=(600, 600),
                heading=street_view_heading,
                pitch=street_view_pitch,
                fov=street_view_fov
            )
            
            if response.ok:
                img_base64 = base64.b64encode(response.content).decode('utf-8')
                street_view_image = f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            logger.error(f"ストリートビュー画像取得エラー: {str(e)}")
    
    return satellite_image, street_view_image

### End of file: backend/utils/geocoding_service.py ###


### backend/utils/maps.py ###

# %%
import requests
from utils.logger import logger


def get_static_map(
    api_key, latitude, longitude, zoom=18, size=(600, 600), map_type="satellite"
):
    """
    Google Maps Static APIを使用して、指定した地点の静止画像を取得します。

    :param api_key: APIキー
    :param latitude: 緯度
    :param longitude: 経度
    :param zoom: ズームレベル（1: 世界、5: 大陸、10: 都市、15: 通り、20: 建物）
    :param size: 画像サイズ（幅, 高さ）最大640x640ピクセル
    :param map_type: マップタイプ（roadmap, satellite, hybrid, terrain）
    """
    logger.debug(
        "静的地図取得リクエスト開始: 緯度=%s, 経度=%s, ズーム=%s",
        latitude,
        longitude,
        zoom,
    )
    base_url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{latitude},{longitude}",
        "zoom": zoom,
        "size": f"{size[0]}x{size[1]}",
        "maptype": map_type,
        "key": api_key,
    }

    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug("静的地図取得成功。ステータスコード: %s", response.status_code)
    else:
        logger.error("静的地図取得失敗。ステータスコード: %s", response.status_code)
    return response


def get_coordinates(api_key, address):
    """
    住所や建物名などのキーワードから緯度経度を取得します。（ジオコーディング）

    :param api_key: APIキー
    :param address: 住所または建物名などのキーワード
    :return: (緯度, 経度) のタプル。取得できなかった場合は None を返します。
    """
    logger.debug("ジオコーディングリクエスト開始: 住所=%s", address)
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug("ジオコーディング成功。ステータスコード: %s", response.status_code)
    else:
        logger.error("ジオコーディング失敗。ステータスコード: %s", response.status_code)
    data = response.json()
    return data


def get_address(api_key, latitude, longitude):
    """
    緯度経度から住所を取得します。（リバースジオコーディング）

    :param api_key: APIキー
    :param latitude: 緯度
    :param longitude: 経度
    :return: 住所（文字列）。取得できなかった場合は None を返します。
    """
    logger.debug(
        "リバースジオコーディングリクエスト開始: 緯度=%s, 経度=%s", latitude, longitude
    )
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"latlng": f"{latitude},{longitude}", "key": api_key}
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug(
"リバースジオコーディング成功。ステータスコード: %s", response.status_code
        )
    else:
        logger.error(
            "リバースジオコーディング失敗。ステータスコード: %s", response.status_code
        )
    data = response.json()
    return data


def get_street_view(
    api_key, latitude, longitude, size=(600, 600), heading=None, pitch=0, fov=90
):
    """
    Google Maps Street View Static APIを使用して、指定した地点のストリートビューの静止画像を取得します。

    :param api_key: APIキー
    :param latitude: 緯度
    :param longitude: 経度
    :param size: 画像サイズ（幅, 高さ）最大640x640ピクセル
    :param heading: カメラの向き（0〜360度）Noneだと自動
    :param pitch: カメラの上下角度（-90〜90度）
    :param fov: 画像の視野（1〜120度）
    """
    logger.debug(
        "ストリートビュー静止画像取得リクエスト開始: 緯度=%s, 経度=%s, heading=%s, pitch=%s, fov=%s",
        latitude,
        longitude,
        heading,
        pitch,
        fov,
    )
    base_url = "https://maps.googleapis.com/maps/api/streetview"
    params = {
        "size": f"{size[0]}x{size[1]}",
        "location": f"{latitude},{longitude}",
        "pitch": pitch,
        "fov": fov,
        "key": api_key,
    }
    if heading is not None:
        params["heading"] = heading
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug(
            "ストリートビュー静止画像取得成功。ステータスコード: %s",
            response.status_code,
        )
    else:
        logger.error(
            "ストリートビュー静止画像取得失敗。ステータスコード: %s",
            response.status_code,
        )
    return response

### End of file: backend/utils/maps.py ###


### backend/utils/common.py ###

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
PORT = int(os.getenv("PORT", '8080'))
FRONTEND_PATH = os.getenv("FRONTEND_PATH")
DEBUG = bool(int(os.getenv("DEBUG", "0")))


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
        logger.debug(
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
            logger.debug("リサイズ後: %dx%dpx", new_width, new_height)
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
        logger.debug(
            "圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
        )
        while len(output_data) > MAX_IMAGE_SIZE and quality > 30:
            quality -= 10
            output = io.BytesIO()
            image.save(output, format=output_format, quality=quality, optimize=True)
            output_data = output.getvalue()
            logger.debug(
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

    logger.debug(f"X-Forwarded-For: {remote_addr}")
    if remote_addr and "," in remote_addr:
        remote_addr = remote_addr.split(",")[0].strip()
    try:
        client_ip = ipaddress.ip_address(remote_addr)
        logger.debug(f"@リクエスト送信元IP: {client_ip}")
    except ValueError:
        time.sleep(0.05)
        raise HTTPException(status_code=400, detail="不正なIPアドレス形式です")

    # ALLOWED_IPSは.envから取得する設定とする
    allowed_tokens = ALLOWED_IPS
    logger.debug(f'許可されたIPアドレスまたはネットワーク: {allowed_tokens}')
    allowed_networks = []
    for token in allowed_tokens.split(","):
        token = token.strip()
        if token:
            logger.debug(f'許可されたIPアドレスまたはネットワーク: {token}')
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

### End of file: backend/utils/common.py ###


### frontend/src/components/Geocoding/GeocodingPage.tsx ###

// src/components/Geocoding/GeocodingPage.tsx
import React, { useState, useEffect, useRef } from "react";
import { useToken } from "../../hooks/useToken";
import * as indexedDBUtils from "../../utils/indexedDBUtils";
import * as Config from "../../config";
import * as Encoding from "encoding-japanese";
import { MapControls } from "./MapControls";
import { imageCache } from "../../utils/imageCache";

// メッセージタイプの定義（WebSocketと互換性を保つ）
enum MessageType {
  GEOCODE_RESULT = "GEOCODE_RESULT",
  IMAGE_RESULT = "IMAGE_RESULT",
  ERROR = "ERROR",
  COMPLETE = "COMPLETE",
}

// メッセージインターフェース
interface Message {
  type: MessageType;
  payload: any;
}

export interface GeoResult {
  query: string;
  status: string;
  formatted_address: string;
  latitude: number | null;
  longitude: number | null;
  location_type: string;
  place_id: string;
  types: string;
  error?: string;
  isCached?: boolean;
  fetchedAt?: number;
  original?: string;
  mode?: "address" | "latlng";
  satelliteImage?: string;
  streetViewImage?: string;
  // 処理状態を示すフラグ
  isProcessing?: boolean;
  imageLoading?: boolean;
}

// TTL取得用の定数
const GOOGLE_MAPS_API_CACHE_TTL = Number(
  Config.getServerConfig().GOOGLE_MAPS_API_CACHE_TTL || 86400000
);

// IndexedDB用の関数（GeocodeCacheDB）
function openCacheDB(): Promise<IDBDatabase> {
  return indexedDBUtils.openDB("GeocodeCacheDB", 1, (db) => {
    if (!db.objectStoreNames.contains("geocodeCache")) {
      db.createObjectStore("geocodeCache", { keyPath: "query" });
    }
  });
}

// キャッシュから結果を取得する関数
async function getCachedResult(query: string): Promise<GeoResult | null> {
  const db = await openCacheDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("geocodeCache", "readonly");
    const store = transaction.objectStore("geocodeCache");
    const req = store.get(query);
    req.onsuccess = () => {
      const result = req.result ? req.result : null;

      // TTLチェック: TTL内のキャッシュデータのみを返す
      if (result && result.fetchedAt) {
        const now = Date.now();
        const age = now - result.fetchedAt;
        if (age < GOOGLE_MAPS_API_CACHE_TTL) {
          resolve(result);
        } else {
          console.log(`キャッシュの有効期限切れ: ${query}, 経過時間=${age}ms`);
          resolve(null);
        }
      } else {
        resolve(null);
      }
    };
    req.onerror = () => reject(req.error);
  });
}

// キャッシュに結果を保存する関数
async function setCachedResult(result: GeoResult): Promise<void> {
  const db = await openCacheDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("geocodeCache", "readwrite");
    const store = transaction.objectStore("geocodeCache");
    const req = store.put(result);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

// 画像キャッシュのヘルパー関数
function getCachedImage(
  lat: number,
  lng: number,
  options: any,
  type: "satellite" | "streetview"
): string | undefined {
  if (!lat || !lng) return undefined;

  if (type === "satellite") {
    return imageCache.get({
      type: "satellite",
      lat,
      lng,
      zoom: options.satelliteZoom,
    });
  } else {
    return imageCache.get({
      type: "streetview",
      lat,
      lng,
      heading: options.streetViewNoHeading ? null : options.streetViewHeading,
      pitch: options.streetViewPitch,
      fov: options.streetViewFov,
    });
  }
}

const GeocodingPage = () => {
  // 入力・結果関連のstate
  const [inputText, setInputText] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const [results, setResults] = useState<GeoResult[]>([]);
  const [inputMode, setInputMode] = useState<"address" | "latlng">("address");
  const [csvEncoding, setCsvEncoding] = useState<"utf8" | "shift-jis">("shift-jis");
  const [progress, setProgress] = useState(0);

  // エラー関連のstate
  const [fetchError, setFetchError] = useState("");
  
  // 地図表示用のstate
  const [showSatellite, setShowSatellite] = useState(false);
  const [showStreetView, setShowStreetView] = useState(false);
  const [satelliteZoom, setSatelliteZoom] = useState(18);
  const [streetViewHeading, setStreetViewHeading] = useState(0);
  const [streetViewPitch, setStreetViewPitch] = useState(0);
  const [streetViewFov, setStreetViewFov] = useState(90);
  const [streetViewNoHeading, setStreetViewNoHeading] = useState(true);

  const token = useToken();

  // リクエストの中止用コントローラー
  const abortControllerRef = useRef<AbortController | null>(null);

  // メッセージ処理関数
  const handleMessage = (message: Message) => {
    console.log(`メッセージ処理: ${message.type}`);
    switch (message.type) {
      case MessageType.GEOCODE_RESULT:
        handleGeocodeResult(message.payload);
        break;
      case MessageType.IMAGE_RESULT:
        handleImageResult(message.payload);
        break;
      case MessageType.ERROR:
        handleError(message.payload);
        break;
      case MessageType.COMPLETE:
        handleComplete(message.payload);
        break;
      default:
        console.warn("不明なメッセージタイプ:", message.type);
    }
  };

  // ジオコーディング結果を処理する関数
  const handleGeocodeResult = (payload: any) => {
    console.log(`ジオコーディング結果受信: index=${payload.index}`);
    const { index, result } = payload;

    setResults((prevResults) => {
      const newResults = [...prevResults];
      // キャッシュデータを保存
      if (!result.isCached) {
        setCachedResult(result).catch((err) =>
          console.error("キャッシュ保存エラー:", err)
        );
      }

      // 画像のロード状態を設定
      if (
        (showSatellite || showStreetView) &&
        result.latitude !== null &&
        result.longitude !== null
      ) {
        result.imageLoading = true;
      }

      // 既存の結果を更新または新しい結果を追加
      if (index < newResults.length) {
        newResults[index] = {
          ...newResults[index],
          ...result,
          isProcessing: false,
        };
      } else {
        newResults.push({ ...result, isProcessing: false });
      }

      return newResults;
    });

    // 進捗状況の更新
    setProgress(payload.progress || 0);
  };

  // 画像結果を処理する関数
  const handleImageResult = (payload: any) => {
    console.log(`画像結果受信: index=${payload.index}`);
    const { index, satelliteImage, streetViewImage } = payload;

    setResults((prevResults) => {
      const newResults = [...prevResults];
      if (index < newResults.length) {
        const result = newResults[index];

        // イメージデータを更新し、ロード状態を解除
        newResults[index] = {
          ...result,
          satelliteImage: satelliteImage || result.satelliteImage,
          streetViewImage: streetViewImage || result.streetViewImage,
          imageLoading: false,
        };

        // 衛星画像をキャッシュ
        if (
          satelliteImage &&
          result.latitude !== null &&
          result.longitude !== null
        ) {
          imageCache.set(
            {
              type: "satellite",
              lat: result.latitude,
              lng: result.longitude,
              zoom: satelliteZoom,
            },
            satelliteImage
          );
        }

        // ストリートビュー画像をキャッシュ
        if (
          streetViewImage &&
          result.latitude !== null &&
          result.longitude !== null
        ) {
          imageCache.set(
            {
              type: "streetview",
              lat: result.latitude,
              lng: result.longitude,
              heading: streetViewNoHeading ? null : streetViewHeading,
              pitch: streetViewPitch,
              fov: streetViewFov,
            },
            streetViewImage
          );
        }
      }
      return newResults;
    });

    // 進捗状況の更新
    setProgress(payload.progress || 0);
  };

  // エラーを処理する関数
  const handleError = (payload: any) => {
    console.error("エラー:", payload);
    alert(`エラーが発生しました: ${payload.message || "不明なエラー"}`);
    setIsSending(false);
    setFetchError(payload.message || "不明なエラー");
  };

  // 処理完了を処理する関数
  const handleComplete = (payload: any) => {
    console.log("処理が完了しました:", payload);
    setIsSending(false);
    setProgress(100);
  };

  // HTTPリクエストを使用してジオコーディングを行う
  const fetchGeocodingResults = async (lines: string[], queryToIndexMap: Map<string, number[]>) => {
    if (!token) {
      alert("認証トークンが取得できません。再ログインしてください。");
      return false;
    }

    try {
      // 重複排除して一意のクエリだけを送信
      const uniqueLines = Array.from(queryToIndexMap.keys());

      // リクエストの設定
      const options = {
        showSatellite,
        showStreetView,
        satelliteZoom,
        streetViewHeading: streetViewNoHeading ? null : streetViewHeading,
        streetViewPitch,
        streetViewFov,
      };

      // APIエンドポイントのURL
      const endpoint = 
        process.env.NODE_ENV === "development" 
          ? "http://localhost:8080/backend/geocoding"
          : "/backend/geocoding";

      // 中止用のコントローラーを作成
      abortControllerRef.current = new AbortController();
      
      // リクエストヘッダー
      const headers = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      };

      // リクエストボディ
      const body = JSON.stringify({
        mode: inputMode,
        lines: uniqueLines,
        options,
      });

      // fetchリクエストを開始
      const response = await fetch(endpoint, {
        method: "POST",
        headers,
        body,
        signal: abortControllerRef.current.signal,
      });

      // エラーチェック
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`APIエラー (${response.status}): ${errorText}`);
      }

      // StreamingResponseを読み込む
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("レスポンスボディを読み取れません");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      // ストリームを読み込む
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // バッファに追加
        buffer += decoder.decode(value, { stream: true });

        // 完全なJSONメッセージを処理
        let newlineIndex;
        while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
          const messageText = buffer.slice(0, newlineIndex);
          buffer = buffer.slice(newlineIndex + 1);

          try {
            const message = JSON.parse(messageText);
            
            // オリジナルインデックスの変換処理
            if (message.type === MessageType.GEOCODE_RESULT || message.type === MessageType.IMAGE_RESULT) {
              const serverIndex = message.payload.index;
              const query = uniqueLines[serverIndex];
              const indices = queryToIndexMap.get(query) || [];
              
              // 各インデックスで結果を更新
              indices.forEach((idx) => {
                const modifiedPayload = {
                  ...message.payload,
                  index: idx,
                };
                
                // 適切なハンドラーを呼び出す
                handleMessage({
                  type: message.type,
                  payload: modifiedPayload,
                });
              });
            } else {
              // その他のメッセージタイプはそのまま処理
              handleMessage(message);
            }
          } catch (e) {
            console.error("JSONパースエラー:", e, messageText);
          }
        }
      }

      return true;
    } catch (error) {
      if (error.name === "AbortError") {
        console.log("リクエストがキャンセルされました");
      } else {
        console.error("ジオコーディングリクエストエラー:", error);
        setFetchError(error.message);
        alert(`エラーが発生しました: ${error.message}`);
      }
      return false;
    }
  };

  // 送信処理
  const handleSendLines = async () => {
    const allLines = inputText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);

    if (allLines.length === 0) return;

    // 画像表示の有無に応じた上限件数を設定
    const maxBatchSize =
      showSatellite || showStreetView
        ? Config.getServerConfig().GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE
        : Config.getServerConfig().GEOCODING_NO_IMAGE_MAX_BATCH_SIZE;

    if (allLines.length > maxBatchSize) {
      alert(
        `入力された件数は${allLines.length}件ですが、1回の送信で取得可能な上限は${maxBatchSize}件です。\n` +
          `件数を減らして再度送信してください。`
      );
      return;
    }

    setIsSending(true);
    setProgress(0);
    setFetchError("");

    // 初期結果配列とクエリーマッピングの準備
    const initialResults: GeoResult[] = [];

    // 重複管理: クエリー -> インデックスリストのマップ
    const queryToIndexMap = new Map<string, number[]>();

    // 先にキャッシュチェックして初期結果を設定
    const timestamp = Date.now();
    const linesToSend: string[] = [];

    // 各行についてキャッシュをチェック
    for (let i = 0; i < allLines.length; i++) {
      const line = allLines[i];

      // キャッシュチェック
      const cachedResult = await getCachedResult(line);

      if (cachedResult && cachedResult.fetchedAt) {
        // キャッシュがある場合は、それを使用
        console.log(
          `キャッシュ利用: ${line}, 取得日時=${new Date(
            cachedResult.fetchedAt
          ).toLocaleString()}`
        );
        initialResults.push({
          ...cachedResult,
          isCached: true,
          imageLoading: false,
        });

        // 画像キャッシュをチェック
        if (
          (showSatellite || showStreetView) &&
          cachedResult.latitude !== null &&
          cachedResult.longitude !== null
        ) {
          const options = {
            satelliteZoom,
            streetViewHeading: streetViewNoHeading ? null : streetViewHeading,
            streetViewPitch,
            streetViewFov,
            streetViewNoHeading,
          };

          let needImageRequest = false;

          // 衛星画像キャッシュをチェック
          if (showSatellite) {
            const cachedSatelliteImage = getCachedImage(
              cachedResult.latitude,
              cachedResult.longitude,
              options,
              "satellite"
            );

            if (cachedSatelliteImage) {
              initialResults[i].satelliteImage = cachedSatelliteImage;
            } else {
              needImageRequest = true;
            }
          }

          // ストリートビュー画像キャッシュをチェック
          if (showStreetView) {
            const cachedStreetViewImage = getCachedImage(
              cachedResult.latitude,
              cachedResult.longitude,
              options,
              "streetview"
            );

            if (cachedStreetViewImage) {
              initialResults[i].streetViewImage = cachedStreetViewImage;
            } else {
              needImageRequest = true;
            }
          }

          // 画像リクエストが必要な場合のみ imageLoading フラグを設定
          if (needImageRequest) {
            initialResults[i].imageLoading = true;

            // クエリーマッピングに追加（画像だけを取得するため）
            if (!queryToIndexMap.has(line)) {
              queryToIndexMap.set(line, [i]);
              linesToSend.push(line);
            } else {
              queryToIndexMap.get(line)?.push(i);
            }
          }
        }
      } else {
        // キャッシュがない場合は、初期状態を設定
        initialResults.push({
          query: line,
          status: "PROCESSING",
          formatted_address: "",
          latitude: null,
          longitude: null,
          location_type: "",
          place_id: "",
          types: "",
          isProcessing: true,
          mode: inputMode as "address" | "latlng",
          fetchedAt: timestamp,
        });

        // クエリーマッピングに追加
        if (!queryToIndexMap.has(line)) {
          queryToIndexMap.set(line, [i]);
          linesToSend.push(line);
        } else {
          queryToIndexMap.get(line)?.push(i);
        }
      }
    }

    // 初期結果を設定
    setResults(initialResults);

    // サーバーに送信するクエリがある場合のみ処理
    if (linesToSend.length > 0) {
      console.log(`重複排除後のクエリ数: ${linesToSend.length}件`);

      // HTTPリクエストを実行
      const success = await fetchGeocodingResults(linesToSend, queryToIndexMap);
      if (!success) {
        setIsSending(false);
      }
    } else {
      // すべてキャッシュヒットの場合は即時完了
      console.log(
        "すべてキャッシュから取得済み。APIリクエストは不要です。"
      );
      // すべての結果で imageLoading フラグを確実に false に設定
      setResults(
        initialResults.map((result) => ({
          ...result,
          imageLoading: false,
        }))
      );
      setIsSending(false);
      setProgress(100);
    }
  };

  // 処理中断ハンドラー
  const handleCancelRequest = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsSending(false);
    }
  };

  // 結果クリアボタンのハンドラー
  const handleClearResults = () => {
    setResults([]);
    setProgress(0);
  };

  // テキストボックスクリアボタンのハンドラー
  const handleClearText = () => {
    setInputText("");
    setLineCount(0);
  };

  // テキストエリアの内容変更時処理
  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputText(text);
    let validLines: string[] = [];
    if (inputMode === "address") {
      validLines = text.split("\n").filter((line) => line.trim().length > 0);
    } else {
      const pattern = /^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/;
      validLines = text
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => {
          const noSpace = line.replace(/\s/g, "");
          return pattern.test(noSpace);
        });
    }
    setLineCount(validLines.length);
  };

  // CSVダウンロード処理
  const handleDownloadCSV = () => {
    if (results.length === 0) return;
    const header = [
      "No.",
      "クエリー",
      "ステータス",
      "Formatted Address",
      "Latitude",
      "Longitude",
      "Location Type",
      "Place ID",
      "Types",
      "エラー",
      "データ取得日時",
      "キャッシュ利用",
    ];
    const rows = results.map((result, index) => [
      index + 1,
      result.query,
      result.status,
      result.formatted_address,
      result.latitude ?? "",
      result.longitude ?? "",
      result.location_type,
      result.place_id,
      result.types,
      result.error || "",
      result.fetchedAt
        ? new Date(result.fetchedAt).toLocaleString("ja-JP")
        : "",
      result.isCached ? "キャッシュ" : "API取得",
    ]);

    const csvContent = [header, ...rows]
      .map((row) =>
        row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")
      )
      .join("\n");

    let blob: Blob;
    if (csvEncoding === "utf8") {
      blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
    } else {
      const codeArray = Encoding.stringToCode(csvContent);
      const sjisArray = Encoding.convert(codeArray, "SJIS");
      blob = new Blob([new Uint8Array(sjisArray)], {
        type: "text/csv;charset=shift_jis",
      });
    }

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "geocoding_results.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4 text-gray-100">
        ジオコーディング
      </h1>

      {/* エラーメッセージの表示 */}
      {fetchError && (
        <div className="mb-4">
          <span className="text-red-400">{fetchError}</span>
        </div>
      )}

      {/* 地図コントロール */}
      <MapControls
        showSatellite={showSatellite}
        showStreetView={showStreetView}
        onShowSatelliteChange={setShowSatellite}
        onShowStreetViewChange={setShowStreetView}
        satelliteZoom={satelliteZoom}
        onSatelliteZoomChange={setSatelliteZoom}
        streetViewHeading={streetViewHeading}
        onStreetViewHeadingChange={setStreetViewHeading}
        streetViewPitch={streetViewPitch}
        onStreetViewPitchChange={setStreetViewPitch}
        streetViewFov={streetViewFov}
        onStreetViewFovChange={setStreetViewFov}
        streetViewNoHeading={streetViewNoHeading}
        onStreetViewNoHeadingChange={setStreetViewNoHeading}
      />

      {/* 入力モード選択 */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-200 mb-2">
          入力モード
        </label>
        <div>
          <label className="mr-4 text-gray-200">
            <input
              type="radio"
              name="inputMode"
              value="address"
              checked={inputMode === "address"}
              onChange={() => setInputMode("address")}
            />{" "}
            住所等⇒緯度経度
          </label>
          <label className="text-gray-200">
            <input
              type="radio"
              name="inputMode"
              value="latlng"
              checked={inputMode === "latlng"}
              onChange={() => setInputMode("latlng")}
            />{" "}
            緯度経度⇒住所
          </label>
        </div>
      </div>

      {/* テキスト入力エリア */}
      <div className="mb-4">
        <div className="mb-2 flex justify-between items-center">
          <label className="text-sm font-medium text-gray-200">
            {inputMode === "address"
              ? "1行毎に住所や施設名等の「キーワード」を入力すると、緯度経度を返します。"
              : "1行毎に「緯度,経度」を入力すると、住所を返します。"}
          </label>
          <button
            onClick={handleClearText}
            disabled={inputText.trim() === ""}
            className="px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50"
          >
            テキストボックスをクリア
          </button>
        </div>
        <textarea
          value={inputText}
          onChange={handleTextChange}
          className="w-full h-64 p-2 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500"
          placeholder={
            inputMode === "address"
              ? "例：札幌市役所"
              : "例：35.6812996,139.7670658"
          }
        />
      </div>

      {/* アクションボタン */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-gray-200">
          有効な行数: <strong>{lineCount}</strong>
        </div>
        <div className="flex items-center space-x-4">
          {/* 送信ボタン（または中止ボタン） */}
          {isSending ? (
            <button
              onClick={handleCancelRequest}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
            >
              中止
            </button>
          ) : (
            <button
              onClick={handleSendLines}
              disabled={lineCount === 0}
              className={`px-4 py-2 text-white rounded transition-colors duration-200 ${
                lineCount === 0
                  ? "bg-blue-400 cursor-not-allowed opacity-50"
                  : "bg-blue-600 hover:bg-blue-700"
              }`}
            >
              送信
            </button>
          )}
          <button
            onClick={handleDownloadCSV}
            disabled={isSending || results.length === 0}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            CSVダウンロード
          </button>
          <div className="flex items-center space-x-2">
            <label className="text-gray-200">
              <input
                type="radio"
                name="csvEncoding"
                value="utf8"
                checked={csvEncoding === "utf8"}
                onChange={() => setCsvEncoding("utf8")}
              />{" "}
              UTF-8
            </label>
            <label className="text-gray-200">
              <input
                type="radio"
                name="csvEncoding"
                value="shift-jis"
                checked={csvEncoding === "shift-jis"}
                onChange={() => setCsvEncoding("shift-jis")}
              />{" "}
              Shift-JIS
            </label>
          </div>
          <button
            onClick={handleClearResults}
            disabled={results.length === 0}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
          >
            結果をクリア
          </button>
        </div>
      </div>

      {/* 進捗バー */}
      {isSending && (
        <div className="w-full bg-gray-700 rounded-full h-4 mb-4">
          <div
            className="bg-blue-600 h-4 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          ></div>
          <div className="text-center text-gray-200 text-sm mt-1">
            {Math.round(progress)}% 完了
          </div>
        </div>
      )}

      {/* 結果テーブル */}
      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-gray-200">
            <thead>
              <tr className="bg-gray-700">
                <th className="px-4 py-2">No.</th>
                <th className="px-4 py-2">クエリー</th>
                <th className="px-4 py-2">状態</th>
                {inputMode === "address" ? (
                  <>
                    <th className="px-4 py-2">緯度</th>
                    <th className="px-4 py-2">経度</th>
                  </>
                ) : (
                  <th className="px-4 py-2">住所</th>
                )}
                {showSatellite && <th className="px-4 py-2">衛星写真</th>}
                {showStreetView && (
                  <th className="px-4 py-2">ストリートビュー</th>
                )}
              </tr>
            </thead>
            <tbody>
              {results.map((result, index) => (
                <tr key={index} className="border-b border-gray-700">
                  <td className="px-4 py-2">{index + 1}</td>
                  <td className="px-4 py-2">
                    {result.original || result.query}
                  </td>
                  <td className="px-4 py-2">
                    {result.isProcessing ? (
                      <span className="inline-block animate-pulse bg-yellow-500 text-gray-900 px-2 py-1 rounded">
                        処理中...
                      </span>
                    ) : result.imageLoading ? (
                      <span className="inline-block animate-pulse bg-blue-500 text-white px-2 py-1 rounded">
                        画像取得中...
                      </span>
                    ) : result.error ? (
                      <span className="inline-block bg-red-500 text-white px-2 py-1 rounded">
                        エラー
                      </span>
                    ) : (
                      <span className="inline-block bg-green-500 text-white px-2 py-1 rounded">
                        完了
                        {result.isCached && " (キャッシュ)"}
                      </span>
                    )}
                  </td>
                  {inputMode === "address" ? (
                    <>
                      <td className="px-4 py-2">
                        {result.latitude !== null
                          ? result.latitude.toFixed(7)
                          : "-"}
                      </td>
                      <td className="px-4 py-2">
                        {result.longitude !== null
                          ? result.longitude.toFixed(7)
                          : "-"}
                      </td>
                    </>
                  ) : (
                    <td className="px-4 py-2">
                      {result.formatted_address || result.error || "-"}
                    </td>
                  )}
                  {showSatellite && (
                    <td className="px-4 py-2">
                      {result.satelliteImage ? (
                        <img
                          src={result.satelliteImage}
                          alt="衛星写真"
                          className="max-w-xs"
                        />
                      ) : result.isProcessing || result.imageLoading ? (
                        <div className="w-64 h-64 bg-gray-700 animate-pulse flex items-center justify-center">
                          <span className="text-gray-400">読み込み中...</span>
                        </div>
                      ) : null}
                    </td>
                  )}
                  {showStreetView && (
                    <td className="px-4 py-2">
                      {result.streetViewImage ? (
                        <img
                          src={result.streetViewImage}
                          alt="ストリートビュー"
                          className="max-w-xs"
                        />
                      ) : result.isProcessing || result.imageLoading ? (
                        <div className="w-64 h-64 bg-gray-700 animate-pulse flex items-center justify-center">
                          <span className="text-gray-400">読み込み中...</span>
                        </div>
                      ) : null}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default GeocodingPage;

### End of file: frontend/src/components/Geocoding/GeocodingPage.tsx ###


### frontend/src/components/Geocoding/MapControls.tsx ###

// src/components/Geocoding/MapControls.tsx
import React from "react";

interface SliderControlProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
}

export const SliderControl: React.FC<SliderControlProps> = ({
  label,
  value,
  onChange,
  min,
  max,
  step,
  disabled = false,
}) => {
  return (
    <div className="flex items-center space-x-2 mb-2">
      <label className="text-gray-200 w-24">{label}</label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1"
      />
      <input
        type="number"
        value={value}
        disabled={disabled}
        onChange={(e) => {
          const val = Number(e.target.value);
          if (val >= min && val <= max) {
            onChange(val);
          }
        }}
        className="w-20 px-2 py-1 bg-gray-700 text-gray-200 rounded"
      />
    </div>
  );
};

interface MapControlsProps {
  disabled?: boolean;
  showSatellite: boolean;
  showStreetView: boolean;
  onShowSatelliteChange: (checked: boolean) => void;
  onShowStreetViewChange: (checked: boolean) => void;
  satelliteZoom: number;
  onSatelliteZoomChange: (value: number) => void;
  streetViewHeading: number;
  onStreetViewHeadingChange: (value: number) => void;
  streetViewPitch: number;
  onStreetViewPitchChange: (value: number) => void;
  streetViewFov: number;
  onStreetViewFovChange: (value: number) => void;
  // 追加: 方角指定を無効にするかどうかのプロパティ
  streetViewNoHeading: boolean;
  onStreetViewNoHeadingChange: (checked: boolean) => void;
}

export const MapControls: React.FC<MapControlsProps> = ({
  disabled = false,
  showSatellite,
  showStreetView,
  onShowSatelliteChange,
  onShowStreetViewChange,
  satelliteZoom,
  onSatelliteZoomChange,
  streetViewHeading,
  onStreetViewHeadingChange,
  streetViewPitch,
  onStreetViewPitchChange,
  streetViewFov,
  onStreetViewFovChange,
  streetViewNoHeading,
  onStreetViewNoHeadingChange,
}) => {
  return (
    <div className="p-4 bg-gray-800 rounded-lg mb-4">
      <div className="flex space-x-4 mb-4">
        <label className="flex items-center space-x-2 text-gray-200">
          <input
            type="checkbox"
            checked={showSatellite}
            disabled={disabled}
            onChange={(e) => onShowSatelliteChange(e.target.checked)}
            className="form-checkbox"
          />
          <span>衛星写真を表示</span>
        </label>
        <label className="flex items-center space-x-2 text-gray-200">
          <input
            type="checkbox"
            checked={showStreetView}
            disabled={disabled}
            onChange={(e) => onShowStreetViewChange(e.target.checked)}
            className="form-checkbox"
          />
          <span>ストリートビューを表示</span>
        </label>
      </div>

      {showSatellite && (
        <div className="mb-4">
          <h3 className="text-gray-200 font-bold mb-2">衛星写真設定</h3>
          <SliderControl
            disabled={disabled}
            label="ズームレベル"
            value={satelliteZoom}
            onChange={onSatelliteZoomChange}
            min={1}
            max={21}
            step={1}
          />
        </div>
      )}

      {showStreetView && (
        <div>
          <h3 className="text-gray-200 font-bold mb-2">ストリートビュー設定</h3>
          {/* 新たに「方角を指定しない」チェックボックスを追加 */}
          <div className="flex items-center space-x-2 mb-2">
            <label className="text-gray-200">
              <input
                type="checkbox"
                checked={streetViewNoHeading}
                disabled={disabled}
                onChange={(e) => onStreetViewNoHeadingChange(e.target.checked)}
                className="form-checkbox"
              />
              方角を指定しない
            </label>
          </div>
          <SliderControl
            disabled={disabled || streetViewNoHeading}
            label="方角"
            value={streetViewHeading}
            onChange={onStreetViewHeadingChange}
            min={0}
            max={360}
            step={1}
          />
          <SliderControl
            disabled={disabled}
            label="上下角度"
            value={streetViewPitch}
            onChange={onStreetViewPitchChange}
            min={-90}
            max={90}
            step={1}
          />
          <SliderControl
            disabled={disabled}
            label="視野角"
            value={streetViewFov}
            onChange={onStreetViewFovChange}
            min={20}
            max={120}
            step={1}
          />
        </div>
      )}
    </div>
  );
};


### End of file: frontend/src/components/Geocoding/MapControls.tsx ###

