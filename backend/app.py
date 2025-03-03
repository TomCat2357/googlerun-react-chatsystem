# app.py
from flask import Flask, request, Response, jsonify, make_response, send_from_directory, abort
from flask_cors import CORS
from firebase_admin import auth, credentials
from dotenv import load_dotenv
import os, json, firebase_admin, asyncio, base64
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.wsgi import WSGIMiddleware
from pydantic import BaseModel
import uvicorn

# 自作モジュールのインポート
from utils.common import (
    logger, process_uploaded_image, limit_remote_addr, 
    handle_chunked_request, require_auth, MAX_IMAGES
)
from utils.websocket_manager import ConnectionManager, WebSocketMessageType, verify_token
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

# FlaskとFastAPIの初期化
app = Flask(__name__)
fastapi_app = FastAPI()

# 接続マネージャのインスタンス作成
manager = ConnectionManager()

# CORS設定
origins = [org for org in os.getenv("ORIGINS", "").split(",")]
if int(os.getenv("DEBUG", 0)):
    origins.append("http://localhost:5173")
logger.info("ORIGINS: %s", origins)
CORS(
    app,
    origins=origins,
    supports_credentials=False,
    expose_headers=["Authorization"],
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "OPTIONS"],
)

# 全エンドポイントに対してIP制限を適用
@app.before_request
def ip_guard():
    limit_remote_addr()

# リクエストモデル
class GeocodeRequest(BaseModel):
    mode: str
    lines: list[str]
    options: Dict[str, Any]

# WebSocketエンドポイント
@fastapi_app.websocket("/ws/geocoding")
async def websocket_geocoding(websocket: WebSocket):
    await websocket.accept()
    
    client_id = f"client_{id(websocket)}"
    
    try:
        # 認証
        decoded_token = await verify_token(websocket)
        if not decoded_token:
            return
        
        # 接続の確立
        await manager.connect(websocket, client_id)
        
        # メッセージの処理
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == WebSocketMessageType.GEOCODE_REQUEST:
                payload = data["payload"]
                mode = payload.get("mode", "address")
                lines = payload.get("lines", [])
                options = payload.get("options", {})
                
                # 上限件数のチェック
                from utils.common import GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE, GEOCODING_NO_IMAGE_MAX_BATCH_SIZE
                max_batch_size = (
                    GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE
                    if options.get("showSatellite") or options.get("showStreetView")
                    else GEOCODING_NO_IMAGE_MAX_BATCH_SIZE
                )
                
                if len(lines) > max_batch_size:
                    await manager.send_error(
                        client_id,
                        f"入力された件数は{len(lines)}件ですが、1回の送信で取得可能な上限は{max_batch_size}件です。"
                    )
                    continue
                
                # 非同期処理の開始
                asyncio.create_task(
                    process_geocoding(
                        manager,
                        client_id=client_id,
                        mode=mode,
                        lines=lines,
                        options=options
                    )
                )
    except WebSocketDisconnect:
        logger.info(f"クライアント切断: {client_id}")
    except Exception as e:
        logger.error(f"WebSocketエラー: {str(e)}", exc_info=True)
    finally:
        manager.disconnect(client_id)

# === 既存のエンドポイント（WebSocket移行対象のRESTfulエンドポイントは削除） ===
@app.route("/backend/config", methods=["GET"])
@require_auth
def get_config(decoded_token: Dict) -> Response:
    try:
        config_values = {
            "MAX_IMAGES": os.getenv("MAX_IMAGES"),
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
        response = make_response(jsonify(config_values))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("Config取得エラー: %s", str(e), exc_info=True)
        error_response = make_response(jsonify({"error": str(e)}))
        error_response.status_code = 500
        return error_response

@app.route("/backend/verify-auth", methods=["GET"])
@require_auth
def verify_auth(decoded_token: Dict) -> Response:
    try:
        logger.info("認証検証開始")
        logger.info("トークンの復号化成功。ユーザー: %s", decoded_token.get("email"))
        response_data = {
            "status": "success",
            "user": {
                "email": decoded_token.get("email"),
                "uid": decoded_token.get("uid"),
            },
            "expire_time": decoded_token.get("exp"),
        }
        logger.info("認証検証完了")
        response = make_response(jsonify(response_data))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        response = make_response(jsonify({"error": str(e)}))
        response.status_code = 401
        return response

@app.route("/backend/chat", methods=["POST"])
@require_auth
@handle_chunked_request
def chat(decoded_token: Dict, assembled_data=None) -> Response:
    logger.info("チャットリクエストを処理中")
    try:
        data = (
            assembled_data if assembled_data is not None else request.get_json() or {}
        )
        messages = data.get("messages", [])
        model = data.get("model")
        logger.info(f"モデル: {model}")
        if model is None:
            raise ValueError("モデル情報が提供されていません")
            
        from utils.common import get_api_key_for_model
        model_api_key = get_api_key_for_model(model)
        error_keyword = "@trigger_error"
        error_flag = False
        for msg in messages:
            content = msg.get("content", "")
            if error_keyword == content:
                error_flag = True
                break
        transformed_messages = []
        for msg in messages:
            if msg.get("role") == "user" and msg.get("images"):
                parts = []
                if msg.get("content"):
                    parts.append({"type": "text", "text": msg["content"]})
                logger.info("チャンク内の画像数: %d", len(msg["images"]))
                images_to_process = msg["images"][:MAX_IMAGES]
                for image in images_to_process:
                    processed_image = process_uploaded_image(image)
                    parts.append(
                        {"type": "image_url", "image_url": {"url": processed_image}}
                    )
                msg["content"] = parts
                msg.pop("images", None)
            transformed_messages.append(msg)
        logger.info(f"選択されたモデル: {model}")
        logger.debug(f"messages: {transformed_messages}")
        if error_flag:
            raise ValueError("意図的なエラーがトリガーされました")
        response = Response(
            common_message_function(
                model=model,
                stream=True,
                messages=transformed_messages,
                api_key=model_api_key,
            ),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "Transfer-Encoding": "chunked"},
        )
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("チャットエラー: %s", e, exc_info=True)
        error_response = make_response(jsonify({"status": "error", "message": str(e)}))
        error_response.status_code = 500
        return error_response

@app.route("/backend/speech2text", methods=["POST"])
@require_auth
@handle_chunked_request
def speech2text(decoded_token: dict, assembled_data=None) -> Response:
    logger.info("音声認識処理開始")
    try:
        data = (
            assembled_data if assembled_data is not None else request.get_json() or {}
        )
        audio_data = data.get("audio_data", "")
        if not audio_data:
            raise ValueError("音声データが提供されていません")

        # ヘッダー除去（"data:audio/～;base64,..."形式の場合）
        if audio_data.startswith("data:"):
            _, audio_data = audio_data.split(",", 1)

        audio_bytes = base64.b64decode(audio_data)
        logger.info("受信した音声サイズ: %d バイト", len(audio_bytes))

        responses = transcribe_streaming_v2(audio_bytes, language_codes=["ja-JP"])

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

        return jsonify(
            {
                "transcription": full_transcript.strip(),
                "timed_transcription": timed_transcription,
            }
        )
    except Exception as e:
        logger.error(f"音声文字起こしエラー: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/backend/generate-image", methods=["POST"])
@require_auth
def generate_image_endpoint(decoded_token: Dict) -> Response:
    data = request.get_json()
    prompt = data.get("prompt")
    model_name = data.get("model_name")
    negative_prompt = data.get("negative_prompt")
    number_of_images = data.get("number_of_images")
    seed = data.get("seed")
    aspect_ratio = data.get("aspect_ratio")
    language = data.get("language", "auto")
    add_watermark = data.get("add_watermark")
    safety_filter_level = data.get("safety_filter_level")
    person_generation = data.get("person_generation")
    kwargs = dict(prompt=prompt, model_name=model_name, negative_prompt=negative_prompt, seed=seed, number_of_images=number_of_images, aspect_ratio=aspect_ratio, language=language, add_watermark=add_watermark, safety_filter_level=safety_filter_level, person_generation=person_generation)
    logger.info(f"generate_image 関数の引数: {kwargs}")
    if None in kwargs.values() and seed is not None:
        NoneParameters = [key for key, value in kwargs.items() if value is None and key != "seed"]
        return jsonify({"error": f"{NoneParameters} is(are) required"}), 400

    try:
        image_list = generate_image(**kwargs)
        if not image_list:
            error_message = "画像生成に失敗しました。プロンプトにコンテンツポリシーに違反する内容（人物表現など）が含まれている可能性があります。別の内容を試してください。"
            logger.warning(error_message)
            return jsonify({"error": error_message}), 500

        encode_images = []
        for img_obj in image_list:
            img_base64 = img_obj._as_base64_string()
            encode_images.append(img_base64)
        return jsonify({"images": encode_images})
    except Exception as e:
        error_message = str(e)
        logger.error(f"画像生成エラー: {error_message}", exc_info=True)
        return jsonify({"error": error_message}), 500

@app.route("/backend/logout", methods=["POST"])
def logout() -> Response:
    try:
        logger.info("ログアウト処理開始")
        response = make_response(
            jsonify({"status": "success", "message": "ログアウトに成功しました"})
        )
        return response, 200
    except Exception as e:
        logger.error("ログアウト処理中にエラーが発生: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 401

# ファイル配信関連エンドポイント
FRONTEND_PATH = os.getenv("FRONTEND_PATH")

@app.route("/assets/<path:path>")
def serve_assets(path):
    logger.info(f"アセットファイルリクエスト: /assets/{path}")
    assets_dir = os.path.join(FRONTEND_PATH, "assets")
    if os.path.exists(assets_dir) and os.path.isfile(os.path.join(assets_dir, path)):
        return send_from_directory(assets_dir, path)
    else:
        logger.warning(f"アセットファイルが見つかりません: {path}")
        if not os.path.exists(assets_dir):
            logger.error(f"アセットディレクトリが存在しません: {assets_dir}")
        abort(404)

@app.route("/vite.svg")
def vite_svg():
    logger.info("vite.svg リクエスト")
    svg_path = os.path.join(FRONTEND_PATH, "vite.svg")
    if os.path.isfile(svg_path):
        return send_from_directory(FRONTEND_PATH, "vite.svg", mimetype="image/svg+xml")
    
    logger.warning(f"vite.svg が見つかりません。確認パス: {svg_path}")
    try:
        logger.info(f"FRONTEND_PATH: {FRONTEND_PATH}")
        logger.info(f"FRONTEND_PATH内のファイル一覧: {os.listdir(FRONTEND_PATH)}")
    except Exception as e:
        logger.error(f"FRONTEND_PATH内のファイル一覧取得エラー: {e}")
    
    abort(404)

@app.route("/")
def index():
    logger.info("インデックスページリクエスト: %s", FRONTEND_PATH)
    return send_from_directory(FRONTEND_PATH, "index.html")

@app.route("/<path:path>")
def static_file(path):
    logger.info(f"パスリクエスト: /{path}")
    return send_from_directory(FRONTEND_PATH, "index.html")

# FastAPIにFlaskアプリをマウント
fastapi_app.mount("/", WSGIMiddleware(app))

if __name__ == "__main__":
    if os.getenv("DEBUG"):
        logger.info("Flaskアプリを起動します DEBUG: %s", bool(int(os.getenv("DEBUG", 0))))
        app.run(host = "0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=bool(int(os.getenv("DEBUG", 0))))
    else:
        logger.info("Uvicornを使用してFastAPIアプリを起動します DEBUG: %s", bool(int(os.getenv("DEBUG", 0))))
        uvicorn.run(
            fastapi_app,
            host="0.0.0.0", 
            port=int(os.getenv("PORT", "8080")), 
            reload=False
        )