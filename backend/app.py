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
from dotenv import load_dotenv
import os, json, asyncio, base64, time


from utils.websocket_manager import (
    ConnectionManager,
    WebSocketMessageType,
    verify_token,
)
from utils.geocoding_service import process_geocoding
from utils.chat_utils import common_message_function
from utils.speech2text import transcribe_streaming_v2
from utils.generate_image import generate_image

# .envファイルを読み込み
load_dotenv("./config/.env.server")
load_dotenv("../.env")

# Firebase Admin SDKの初期化
try:
    # 初期化されているかチェック
    firebase_admin.get_app()
    logger.info("Firebase既に初期化済み")
except ValueError:
    # 初期化されていない場合のみ初期化
    client_secret_path = "./credentials/KKH_client_secret.json"
    if os.path.exists(client_secret_path):
        logger.info(f"Firebase認証情報を読み込み: {client_secret_path}")
        cred = credentials.Certificate(client_secret_path)
        firebase_admin.initialize_app(cred)  # 名前を指定しない
    else:
        logger.info("Firebase認証情報なしで初期化")
        firebase_admin.initialize_app()  # 名前を指定しない

# FastAPIアプリケーションの初期化
app = FastAPI()

# 接続マネージャのインスタンス作成
manager = ConnectionManager()

# CORS設定
origins = [org for org in os.getenv("ORIGINS", "").split(",")]
if int(os.getenv("DEBUG", 0)):
    origins.append("http://localhost:5173")
logger.info("ORIGINS: %s", origins)

# FastAPIのCORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
    logger.info("WebSocket接続リクエスト受信")
    await websocket.accept()

    client_id = f"client_{id(websocket)}"
    logger.info(f"WebSocketクライアントID割り当て: {client_id}")

    try:
        # 接続の確立
        await manager.connect(websocket, client_id)
        logger.info(f"クライアント {client_id} が接続しました")
        # 認証処理を復活させる
        logger.info("WebSocket認証処理開始")
        decoded_token = await verify_token(websocket)
        if not decoded_token:
            logger.error("WebSocket認証失敗")
            await manager.send_error(client_id, "認証に失敗しました")
            return

        logger.info(f"WebSocket認証成功: {decoded_token.get('email')}")

        # メッセージの処理
        while True:
            logger.info("WebSocketメッセージ待機中")
            data = await websocket.receive_json()
            logger.info(f"WebSocketメッセージ受信: {data.get('type', 'unknown')}")

            if data.get("type") == WebSocketMessageType.GEOCODE_REQUEST:
                payload = data.get("payload", {})
                mode = payload.get("mode", "address")
                lines = payload.get("lines", [])
                options = payload.get("options", {})

                # 上限件数のチェック
                from utils.common import (
                    GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE,
                    GEOCODING_NO_IMAGE_MAX_BATCH_SIZE,
                )

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
        logger.info(f"クライアント切断: {client_id}")
    except Exception as e:
        logger.error(f"WebSocketエラー: {str(e)}", exc_info=True)
    finally:
        try:
            manager.disconnect(client_id)
            logger.info(f"クライアント {client_id} との接続を解除しました")
        except Exception as e:
            logger.error(f"接続解除エラー: {str(e)}")


# テスト用のWebSocketエンドポイント
@app.websocket("/ws/echo")
async def websocket_echo(websocket: WebSocket):
    logger.info("Echoテスト: WebSocket接続リクエスト受信")
    await websocket.accept()
    logger.info("Echoテスト: WebSocket接続確立")
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Echoテスト: メッセージ受信: {data}")
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        logger.info("Echoテスト: クライアント切断")
    except Exception as e:
        logger.error(f"Echoテスト: エラー: {str(e)}", exc_info=True)


@app.get("/backend/config")
async def get_config(current_user: Dict = Depends(get_current_user)):
    try:
        config_values = {
            "MAX_IMAGES": os.getenv("MAX_IMAGES"),
            "MAX_AUDIO_FILES": os.getenv("MAX_AUDIO_FILES"),  # 音声ファイル最大数
            "MAX_TEXT_FILES": os.getenv("MAX_TEXT_FILES"),    # テキストファイル最大数
            "MAX_LONG_EDGE": os.getenv("MAX_LONG_EDGE"),
            "MAX_IMAGE_SIZE": os.getenv("MAX_IMAGE_SIZE"),
            "MAX_PAYLOAD_SIZE": os.getenv("MAX_PAYLOAD_SIZE"),
            "GOOGLE_MAPS_API_CACHE_TTL": os.getenv("GOOGLE_MAPS_API_CACHE_TTL"),
            "GEOCODING_NO_IMAGE_MAX_BATCH_SIZE": os.getenv(
                "GEOCODING_NO_IMAGE_MAX_BATCH_SIZE"
            ),
            "GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE": os.getenv(
                "GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE"
            ),
            "SPEECH_CHUNK_SIZE": os.getenv("SPEECH_CHUNK_SIZE"),
            "SPEECH_MAX_SECONDS": os.getenv("SPEECH_MAX_SECONDS"),
            "MODELS": os.getenv("MODELS"),
            "IMAGEN_MODELS": os.getenv("IMAGEN_MODELS"),
            "IMAGEN_NUMBER_OF_IMAGES": os.getenv("IMAGEN_NUMBER_OF_IMAGES"),
            "IMAGEN_ASPECT_RATIOS": os.getenv("IMAGEN_ASPECT_RATIOS"),
            "IMAGEN_LANGUAGES": os.getenv("IMAGEN_LANGUAGES"),
            "IMAGEN_ADD_WATERMARK": os.getenv("IMAGEN_ADD_WATERMARK"),
            "IMAGEN_SAFETY_FILTER_LEVELS": os.getenv("IMAGEN_SAFETY_FILTER_LEVELS"),
            "IMAGEN_PERSON_GENERATIONS": os.getenv("IMAGEN_PERSON_GENERATIONS"),
        }
        return config_values
    except Exception as e:
        logger.error("Config取得エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backend/verify-auth")
async def verify_auth(current_user: Dict = Depends(get_current_user)):
    try:
        logger.info("認証検証開始")
        logger.info("トークンの復号化成功。ユーザー: %s", current_user.get("email"))
        response_data = {
            "status": "success",
            "user": {
                "email": current_user.get("email"),
                "uid": current_user.get("uid"),
            },
            "expire_time": current_user.get("exp"),
        }
        logger.info("認証検証完了")
        return response_data
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))


# チャンクデータ処理関数を修正
async def process_chunked_data(data: Dict[str, Any]):
    from utils.common import CHUNK_STORE

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
        logger.info(
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
            logger.info("期限切れチャンクを削除: %s", expired_id)

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
            logger.info("全チャンク受信完了。データ組み立て開始: %s", chunk_id)

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
                logger.info(
                    "バイナリデータ組み立て完了: %.2f KB", len(assembled_bytes) / 1024
                )
                return {"binary_data": assembled_bytes}

            # テキストデータの場合はUTF-8としてデコードしJSONとしてパース
            try:
                assembled_str = assembled_bytes.decode("utf-8")
                parsed_json = json.loads(assembled_str)
                logger.info("JSONデータ組み立て完了")
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
    logger.info("チャットリクエストを処理中")
    try:
        # リクエストボディの読み込み
        body = await request.json()

        # チャンク処理の確認
        if body.get("chunked"):
            logger.info("チャンクされたデータです")
            try:
                # チャンクデータの処理
                data = await process_chunked_data(body)

                # 追加: 中間チャンクレスポンスの場合はそのまま返す
                if data.get("status") == "chunk_received":
                    logger.info(
                        f"中間チャンク処理: {data.get('received')}/{data.get('total')}"
                    )
                    return data

            except Exception as e:
                logger.error("チャンク組み立てエラー: %s", str(e), exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
        else:
            logger.info("チャンクされていないデータです")
            data = body

        messages = data.get("messages", [])
        model = data.get("model")
        logger.info(f"モデル: {model}")

        if model is None:
            raise HTTPException(
                status_code=400, detail="モデル情報が提供されていません"
            )

        from utils.common import get_api_key_for_model

        model_api_key = get_api_key_for_model(model)
        error_keyword = "@trigger_error"
        error_flag = False

        for msg in messages:
            content = msg.get("content", "")
            if error_keyword == content:
                error_flag = True
                break

        # 各ユーザーメッセージの音声ファイルをフィルタリング
        last_audio_file = None
        for msg in messages:
            if msg.get("role") == "user" and "audioFiles" in msg and msg["audioFiles"]:
                last_audio_file = msg["audioFiles"][-1]  # 最後の音声ファイルを保存
                msg["audioFiles"] = []  # すべての音声ファイルを一旦クリア
        
        # 最後の音声ファイルがある場合、最後のユーザーメッセージに追加
        if last_audio_file:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    messages[i]["audioFiles"] = [last_audio_file]
                    break

        # app.py のメッセージ変換処理部分の修正

        # メッセージ変換処理を更新
        transformed_messages = []
        for msg in messages:
            # ユーザーメッセージに添付ファイルがある場合の処理
            if msg.get("role") == "user":
                # 最後の音声ファイルがある場合、それを特別に処理
                if "audioFiles" in msg and msg["audioFiles"]:
                    # 音声ファイルのMIMEタイプを確実に保存
                    for audio_file in msg["audioFiles"]:
                        if "content" in audio_file and audio_file["content"].startswith("data:"):
                            mime_parts = audio_file["content"].split(",", 1)[0]
                            if ";" in mime_parts and ":" in mime_parts:
                                audio_file["mime_type"] = mime_parts.split(":", 1)[1].split(";", 1)[0]
                            audio_file["data"] = audio_file["content"].split(",", 1)[1]
                
                # prepare_message_for_ai を使ってメッセージ全体を変換
                processed_msg = prepare_message_for_ai(msg)
                transformed_messages.append(processed_msg)
            else:
                # システムメッセージまたはアシスタントメッセージはそのまま
                transformed_messages.append(msg)
        logger.info(f"選択されたモデル: {model}")
        logger.debug(f"messages: {transformed_messages}")

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
    logger.info("音声認識処理開始")
    try:
        # リクエストボディの読み込み
        body = await request.json()

        # チャンク処理の確認
        if body.get("chunked"):
            logger.info("チャンクされたデータです")
            try:
                # チャンクデータの処理（isBinaryフラグを追加）
                body["isBinary"] = True  # 音声データはバイナリとして処理
                data = await process_chunked_data(body)

                # 中間ステータスのチェック - これが重要な修正部分
                if data.get("status") == "chunk_received":
                    # 中間チャンクの場合は、そのままステータスを返す
                    logger.info(
                        f"チャンク中間状態: {data.get('received')}/{data.get('total')} 受信済み"
                    )
                    return data

                # バイナリデータが返された場合の処理
                if "binary_data" in data:
                    audio_bytes = data["binary_data"]
                    logger.info(
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
            logger.info("チャンクされていないデータです")
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
            logger.info(f"受信した音声サイズ: {len(audio_bytes) / 1024:.2f} KB")
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
            logger.info("音声認識処理を開始します")
            responses = transcribe_streaming_v2(audio_bytes, language_codes=["ja-JP"])
            logger.info("音声認識完了")
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

        logger.info(
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
    logger.info(f"generate_image 関数の引数: {kwargs}")

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
        logger.info("ログアウト処理開始")
        return {"status": "success", "message": "ログアウトに成功しました"}
    except Exception as e:
        logger.error("ログアウト処理中にエラーが発生: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))


# 静的ファイル配信設定
FRONTEND_PATH = os.getenv("FRONTEND_PATH", "../frontend/dist")

# 静的ファイルのマウント
app.mount(
    "/assets",
    StaticFiles(directory=os.path.join(FRONTEND_PATH, "assets")),
    name="assets",
)


@app.get("/vite.svg")
async def vite_svg():
    logger.info("vite.svg リクエスト")
    svg_path = os.path.join(FRONTEND_PATH, "vite.svg")
    if os.path.isfile(svg_path):
        return FileResponse(svg_path, media_type="image/svg+xml")

    logger.warning(f"vite.svg が見つかりません。確認パス: {svg_path}")
    try:
        logger.info(f"FRONTEND_PATH: {FRONTEND_PATH}")
        logger.info(f"FRONTEND_PATH内のファイル一覧: {os.listdir(FRONTEND_PATH)}")
    except Exception as e:
        logger.error(f"FRONTEND_PATH内のファイル一覧取得エラー: {e}")

    raise HTTPException(status_code=404, detail="ファイルが見つかりません")


@app.get("/")
async def index():
    logger.info("インデックスページリクエスト: %s", FRONTEND_PATH)
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))


@app.get("/{path:path}")
async def static_file(path: str):
    logger.info(f"パスリクエスト: /{path}")
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))


if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config
    
    # Hypercornの設定
    config = Config()
    config.bind = [f"0.0.0.0:{int(os.getenv('PORT', '8080'))}"]
    config.loglevel = "info" if not int(os.getenv("DEBUG", 0)) else "debug"
    config.accesslog = '-'
    config.errorlog = '-'
    config.workers = 1
    
    # SSL/TLS設定（証明書と秘密鍵のパスを指定）
    cert_path = os.getenv("SSL_CERT_PATH")
    key_path = os.getenv("SSL_KEY_PATH")
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        config.certfile = cert_path
        config.keyfile = key_path
        # SSLプロトコルを明示的に設定して安定性を向上
        config.ciphers = "HIGH:!aNULL:!MD5"
        logger.info("SSL/TLSが有効化されました")
    else:
        logger.warning("SSL/TLS証明書が見つかりません。HTTP/1.1のみで動作します")
    
    # HTTP/2を有効化
    config.alpn_protocols = ["h2", "http/1.1"]
    
    logger.info(
        "Hypercornを使用してFastAPIアプリを起動します（HTTP/2対応） DEBUG: %s",
        bool(int(os.getenv("DEBUG", 0))),
    )
    
    # Hypercornでアプリを起動
    import asyncio
    asyncio.run(hypercorn.asyncio.serve(app, config))
