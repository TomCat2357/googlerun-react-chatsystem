#%%
# app.py
from flask import Flask, request, Response, jsonify, make_response, send_from_directory, abort
from flask_cors import CORS
from firebase_admin import auth, credentials
from dotenv import load_dotenv
from functools import wraps
import os, json, firebase_admin, io, base64, ipaddress, time
from PIL import Image
from typing import Dict, Optional, Callable, List
from litellm import completion
from utils.logger import *
from utils.maps import *
from utils.speech2text import transcribe_streaming_v2
from utils.generate_image import generate_image
import uvicorn
from asgiref.wsgi import WsgiToAsgi
from google.cloud import secretmanager
    



# .envファイルを読み込み
load_dotenv("./config/.env.server")
load_dotenv("../.env")


# 環境変数から設定を読み込み
MAX_IMAGES = int(os.getenv("MAX_IMAGES"))
MAX_LONG_EDGE = int(os.getenv("MAX_LONG_EDGE"))
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE"))
GOOGLE_MAPS_API_CACHE_TTL = int(os.getenv("GOOGLE_MAPS_API_CACHE_TTL"))
GEOCODING_NO_IMAGE_MAX_BATCH_SIZE = int(os.getenv("GEOCODING_NO_IMAGE_MAX_BATCH_SIZE"))
GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE = int(os.getenv("GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE"))
SPEECH_MAX_SECONDS = int(os.getenv("SPEECH_MAX_SECONDS"))
MAX_PAYLOAD_SIZE = int(os.getenv("MAX_PAYLOAD_SIZE"))

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

        

app = Flask(__name__)

# ===== IPアドレス制限機能（gateway.pyから移植） =====
# ALLOWED_IPSは.envから取得する設定とする
allowed_tokens = os.getenv('ALLOWED_IPS', '')
allowed_networks = []
for token in allowed_tokens.split(','):
    token = token.strip()
    if token:
        try:
            if '/' in token:
                network = ipaddress.ip_network(token, strict=False)
            else:
                ip = ipaddress.ip_address(token)
                network = ipaddress.ip_network(f"{ip}/{'32' if ip.version == 4 else '128'}")
            allowed_networks.append(network)
        except ValueError as e:
            logger.error(f"無効なIPアドレスまたはネットワーク形式: {token}, エラー: {e}")

# Secret Managerからシークレットを取得するための関数
def access_secret(secret_id, version_id="latest"):
    """
    Secret Managerからシークレットを取得する関数
    """
    try:
        logger.info(f"Secret Managerから{secret_id}を取得しています")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            # プロジェクトIDが環境変数に設定されていない場合はメタデータから取得
            import requests
            project_id = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"}
            ).text
        
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(f"Secret Managerからのシークレット取得に失敗: {str(e)}", exc_info=True)
        return None

# Google Maps APIキーを取得するための関数
def get_google_maps_api_key():
    """
    環境変数からGoogle Maps APIキーを取得し、なければSecret Managerから取得する
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.info("環境変数にGoogle Maps APIキーが設定されていないため、Secret Managerから取得します")
        api_key = access_secret("google-maps-api-key")
        if not api_key:
            raise Exception("Google Maps APIキーが見つかりません")
    return api_key

def limit_remote_addr():
    """リクエスト送信元IPが許可リストに含まれていなければ403を返す"""
    remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr)
    logger.info(f"X-Forwarded-For: {remote_addr}")
    if remote_addr and ',' in remote_addr:
        remote_addr = remote_addr.split(',')[0].strip()
    try:
        client_ip = ipaddress.ip_address(remote_addr)
        logger.info(f"リクエスト送信元IP: {client_ip}")
    except ValueError:
        time.sleep(0.05)
        abort(400, description="不正なIPアドレス形式です")
    
    # IPがいずれかの許可されたネットワークに含まれているかチェック
    for network in allowed_networks:
        if client_ip in network:
            return  # 許可されている場合、処理継続
    
    time.sleep(0.05)
    abort(403, description="アクセスが許可されていません")

# 全エンドポイントに対してIP制限を適用
@app.before_request
def ip_guard():
    limit_remote_addr()
# ===== IPアドレス制限機能 終了 =====

# グローバルなチャンク保存用辞書
CHUNK_STORE = {}

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


def handle_chunked_request(function: Callable) -> Callable:
    @wraps(function)
    def decorated_function(*args, **kwargs) -> Response:
        logger.info("MAX_PAYLOAD_SIZE: %s", MAX_PAYLOAD_SIZE)
        data = request.get_json() or {}
        if data.get("chunked"):
            logger.info("チャンクされたデータです")
            try:
                chunk_id = data.get("chunkId")
                chunk_index = data.get("chunkIndex")
                total_chunks = data.get("totalChunks")
                chunk_data_b64 = data.get("chunkData")
                if (
                    not chunk_id
                    or chunk_index is None
                    or not total_chunks
                    or not chunk_data_b64
                ):
                    raise ValueError("チャンク情報が不足しています")
                # base64デコードしてバイナリ取得
                chunk_data = base64.b64decode(chunk_data_b64)
                if chunk_id not in CHUNK_STORE:
                    CHUNK_STORE[chunk_id] = {}
                CHUNK_STORE[chunk_id][chunk_index] = chunk_data
                logger.info(
                    "チャンク受信: %s - インデックス %d/%d",
                    chunk_id,
                    chunk_index,
                    total_chunks,
                )
                if len(CHUNK_STORE[chunk_id]) < total_chunks:
                    return (
                        jsonify(
                            {
                                "status": "chunk_received",
                                "chunkId": chunk_id,
                                "received": len(CHUNK_STORE[chunk_id]),
                                "total": total_chunks,
                            }
                        ),
                        200,
                    )
                # 全チャンク受信済みの場合、順次再構築
                assembled_bytes = b"".join(
                    CHUNK_STORE[chunk_id][i] for i in range(total_chunks)
                )
                del CHUNK_STORE[chunk_id]
                assembled_str = assembled_bytes.decode("utf-8")
                data = json.loads(assembled_str)
                logger.info("全チャンク受信完了: %s", chunk_id)
                kwargs["assembled_data"] = data
            except Exception as e:
                logger.error("チャンク組み立てエラー: %s", str(e), exc_info=True)
                return jsonify({"status": "error", "message": str(e)}), 500
        else:
            logger.info("チャンクされていないデータです")
        return function(*args, **kwargs)

    return decorated_function


def process_uploaded_image(image_data: str) -> str:
    try:
        header = None
        if image_data.startswith("data:"):
            header, image_data = image_data.split(",", 1)
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        width, height = image.size
        logger.info(
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
            logger.info("リサイズ後: %dx%dpx", new_width, new_height)
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
        logger.info(
            "圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
        )
        while len(output_data) > MAX_IMAGE_SIZE and quality > 30:
            quality -= 10
            output = io.BytesIO()
            image.save(output, format=output_format, quality=quality, optimize=True)
            output_data = output.getvalue()
            logger.info(
                "再圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
            )
        processed_base64 = base64.b64encode(output_data).decode("utf-8")
        return f"data:{mime_type};base64,{processed_base64}"
    except Exception as e:
        logger.error("画像処理エラー: %s", str(e), exc_info=True)
        return image_data


def get_api_key_for_model(model: str) -> Optional[str]:
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, "")


def common_message_function(
    *, model: str, messages: List, stream: bool = False, **kwargs
):
    if stream:

        def chat_stream():
            for i, text in enumerate(
                completion(messages=messages, model=model, stream=True, **kwargs)
            ):
                if not i:
                    yield
                yield text["choices"][0]["delta"].get("content", "") or ""

        cs = chat_stream()
        cs.__next__()
        return cs
    else:
        return completion(messages=messages, model=model, stream=False, **kwargs)[
            "choices"
        ][0]["message"]["content"]


def require_auth(function: Callable) -> Callable:
    @wraps(function)
    def decorated_function(*args, **kwargs) -> Response:
        try:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.warning("トークンが見つかりません")
                return jsonify({"error": "認証が必要です"}), 401
            token = auth_header.split("Bearer ")[1]
            decoded_token: Dict = auth.verify_id_token(token, clock_skew_seconds=60)
            response: Response = function(decoded_token, *args, **kwargs)
            return response
        except Exception as e:
            logger.error("認証エラー: %s", str(e), exc_info=True)
            response = make_response(jsonify({"error": str(e)}))
            response.status_code = 401
            return response

    return decorated_function


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


@app.route("/backend/models", methods=["GET"])
@require_auth
def get_models(decoded_token: Dict) -> Response:
    try:
        logger.info("モデル一覧取得処理を開始")
        raw_models = os.getenv("MODELS", "")
        logger.info(f"環境変数 MODELS の値: {raw_models}")
        model_list = [m.strip() for m in raw_models.split(",") if m.strip()]
        logger.info(f"モデル一覧: {model_list}")
        response = make_response(jsonify({"models": model_list}))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error(f"モデル一覧取得中にエラーが発生しました: {e}", exc_info=True)
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


@app.route("/backend/address2coordinates", methods=["POST"])
@require_auth
def query2coordinates(decoded_token: Dict) -> Response:
    try:
        data = request.get_json() or {}
        lines = data.get("lines", [])
        logger.info("受信したクエリーリスト: %s", lines)

        # Google Maps APIキーを取得
        google_maps_api_key = get_google_maps_api_key()

        unique_queries = {}
        for line in lines:
            query = line.strip()
            if not query:
                continue
            if query not in unique_queries:
                unique_queries[query] = None

        for query in unique_queries.keys():
            geocode_data = get_coordinates(google_maps_api_key, query)
            if geocode_data.get("status") == "OK" and geocode_data.get("results"):
                result = geocode_data["results"][0]
                location = result["geometry"]["location"]
                unique_queries[query] = {
                    "query": query,
                    "status": geocode_data.get("status"),
                    "formatted_address": result.get("formatted_address", ""),
                    "latitude": location.get("lat"),
                    "longitude": location.get("lng"),
                    "location_type": result["geometry"].get("location_type", ""),
                    "place_id": result.get("place_id", ""),
                    "types": ", ".join(result.get("types", [])),
                    "error": "",
                }
            else:
                unique_queries[query] = {
                    "query": query,
                    "status": geocode_data.get("status", "エラー"),
                    "formatted_address": "",
                    "latitude": None,
                    "longitude": None,
                    "location_type": "",
                    "place_id": "",
                    "types": "",
                    "error": geocode_data.get("status", "エラー"),
                }

        results = []
        for line in lines:
            query = line.strip()
            if not query:
                continue
            results.append(unique_queries[query])
        response = make_response(jsonify({"status": "success", "results": results}))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("ジオコーディング処理エラー: %s", str(e), exc_info=True)
        error_response = make_response(jsonify({"error": str(e)}))
        error_response.status_code = 500
        return error_response


@app.route("/backend/latlng2query", methods=["POST"])
@require_auth
def latlng2query(decoded_token: Dict) -> Response:
    try:
        data = request.get_json() or {}
        lines = data.get("lines", [])
        logger.info("受信した緯度経度リスト: %s", lines)
        
        # Google Maps APIキーを取得
        google_maps_api_key = get_google_maps_api_key()

        unique_lines = {}
        for line in lines:
            query = line.strip()
            if not query:
                continue
            if query not in unique_lines:
                unique_lines[query] = None

        for line in unique_lines.keys():
            parts = line.split(",")
            if len(parts) != 2:
                unique_lines[line] = {
                    "query": line,
                    "status": "INVALID_FORMAT",
                    "formatted_address": "",
                    "latitude": None,
                    "longitude": None,
                    "location_type": "",
                    "place_id": "",
                    "types": "",
                    "error": "無効な形式",
                }
            else:
                try:
                    lat = float(parts[0])
                    lng = float(parts[1])
                except ValueError:
                    unique_lines[line] = {
                        "query": line,
                        "status": "INVALID_FORMAT",
                        "formatted_address": "",
                        "latitude": None,
                        "longitude": None,
                        "location_type": "",
                        "place_id": "",
                        "types": "",
                        "error": "数値変換エラー",
                    }
                    continue
                if lat < -90 or lat > 90 or lng < -180 or lng > 180:
                    unique_lines[line] = {
                        "query": line,
                        "status": "INVALID_RANGE",
                        "formatted_address": "",
                        "latitude": lat,
                        "longitude": lng,
                        "location_type": "",
                        "place_id": "",
                        "types": "",
                        "error": "範囲外",
                    }
                    continue
                geocode_data = get_address(google_maps_api_key, lat, lng)
                if geocode_data.get("status") == "OK" and geocode_data.get("results"):
                    result = geocode_data["results"][0]
                    location = result["geometry"]["location"]
                    unique_lines[line] = {
                        "query": line,
                        "status": geocode_data.get("status"),
                        "formatted_address": result.get("formatted_address", ""),
                        "latitude": location.get("lat"),
                        "longitude": location.get("lng"),
                        "location_type": result["geometry"].get("location_type", ""),
                        "place_id": result.get("place_id", ""),
                        "types": ", ".join(result.get("types", [])),
                        "error": "",
                    }
                else:
                    unique_lines[line] = {
                        "query": line,
                        "status": geocode_data.get("status", "エラー"),
                        "formatted_address": "",
                        "latitude": None,
                        "longitude": None,
                        "location_type": "",
                        "place_id": "",
                        "types": "",
                        "error": geocode_data.get("status", "エラー"),
                    }
        results = []
        for line in lines:
            query = line.strip()
            if not query:
                continue
            results.append(unique_lines[query])
        response = make_response(jsonify({"status": "success", "results": results}))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("リバースジオコーディング処理エラー: %s", str(e), exc_info=True)
        error_response = make_response(jsonify({"error": str(e)}))
        error_response.status_code = 500
        return error_response





@app.route("/backend/static-map", methods=["GET"])
@require_auth
def get_static_map_image(decoded_token: Dict) -> Response:
    try:
        latitude = float(request.args.get("latitude"))
        longitude = float(request.args.get("longitude"))
        zoom = int(request.args.get("zoom", 18))
        width = int(request.args.get("width", 600))
        height = int(request.args.get("height", 600))
        map_type = request.args.get("maptype", "satellite")

        # Google Maps APIキーを取得
        google_maps_api_key = get_google_maps_api_key()

        response = get_static_map(
            google_maps_api_key,
            latitude,
            longitude,
            zoom=zoom,
            size=(width, height),
            map_type=map_type,
        )

        if not response.ok:
            raise Exception(f"Maps API error: {response.status_code}")

        return Response(
            response.content,
            mimetype="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=31536000",
                "Content-Type": "image/jpeg",
            },
        )
    except Exception as e:
        logger.error("静的地図取得エラー: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/backend/street-view", methods=["GET"])
@require_auth
def get_street_view_image(decoded_token: Dict) -> Response:
    try:
        latitude = float(request.args.get("latitude"))
        longitude = float(request.args.get("longitude"))
        heading = request.args.get("heading")
        if heading == "null":
            heading = None
        else:
            heading = float(request.args.get("heading", 0))
        pitch = float(request.args.get("pitch", 0))
        fov = float(request.args.get("fov", 90))
        width = int(request.args.get("width", 600))
        height = int(request.args.get("height", 600))

        # Google Maps APIキーを取得
        google_maps_api_key = get_google_maps_api_key()

        response = get_street_view(
            google_maps_api_key,
            latitude,
            longitude,
            size=(width, height),
            heading=heading,
            pitch=pitch,
            fov=fov,
        )

        if not response.ok:
            raise Exception(f"Street View API error: {response.status_code}")

        return Response(
            response.content,
            mimetype="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=31536000",
                "Content-Type": "image/jpeg",
            },
        )
    except Exception as e:
        logger.error("ストリートビュー取得エラー: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


# ======= 音声認識エンドポイント（チャンクアップロード対応） =======
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

        # チャンクアップロードを利用するため、SPEECH_CHUNK_SIZEの制限は解除

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
        # 画像生成の実行
        image_list = generate_image(**kwargs)
        if not image_list:
            # generate_image関数で既にエラーメッセージを生成して例外をスローしているはずなので
            # ここには到達しないはず。万が一のために同じメッセージを使用
            error_message = "画像生成に失敗しました。プロンプトにコンテンツポリシーに違反する内容（人物表現など）が含まれている可能性があります。別の内容を試してください。"
            logger.warning(error_message)
            return jsonify({"error": error_message}), 500

        # 画像エンコード処理
        encode_images = []
        for img_obj in image_list:
            img_base64 = img_obj._as_base64_string()
            encode_images.append(img_base64)
        return jsonify({"images": encode_images})
    except Exception as e:
        # 例外をキャッチして詳細なエラーメッセージをそのまま転送
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
# Viteファビコンルート
@app.route("/vite.svg")
def vite_svg():
    logger.info("vite.svg リクエスト")
    svg_path = os.path.join(FRONTEND_PATH, "vite.svg")
    if os.path.isfile(svg_path):
        # 明示的にMIMEタイプを指定
        return send_from_directory(FRONTEND_PATH, "vite.svg", mimetype="image/svg+xml")
    
    logger.warning(f"vite.svg が見つかりません。確認パス: {svg_path}")
    # ファイルが見つからない場合はFRONTEND_PATHの内容をログに出力
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
#@require_auth
def static_file(path):
    logger.info(f"パスリクエスト: /{path}")
    return send_from_directory(FRONTEND_PATH, "index.html")

#%%
if __name__ == "__main__":
    if os.getenv("DEBUG"):
        logger.info("Flaskアプリを起動します DEBUG: %s", bool(int(os.getenv("DEBUG", 0))))
        app.run(host = "0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=bool(int(os.getenv("DEBUG", 0))))
    else:
        logger.info("Uvicornを使用してFlaskアプリを起動します DEBUG: %s", bool(int(os.getenv("DEBUG", 0))))
        asgi_app = WsgiToAsgi(app)
        uvicorn.run(
            asgi_app,
            host="0.0.0.0", 
            port=int(os.getenv("PORT", "8080")), 
            reload=False
        )