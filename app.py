# app.py
# %%
from flask import Flask, request, Response, jsonify, make_response, send_from_directory
from flask_cors import CORS
from firebase_admin import auth, credentials
from dotenv import load_dotenv
from functools import wraps
import os, json, firebase_admin, io, base64
from PIL import Image
from typing import Dict, Union, Optional, Tuple, Callable, Any, List
from litellm import completion, token_counter
from backend.utils.logger import *
from backend.utils.maps import *  # maps.py の関数群をインポート

# .envファイルを読み込み
load_dotenv("./backend/config/.env")

# 環境変数から画像処理設定を読み込む
MAX_IMAGES = int(os.getenv("MAX_IMAGES"))
MAX_LONG_EDGE = int(os.getenv("MAX_LONG_EDGE"))
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE"))  # デフォルト5MB

# Firebase Admin SDKの初期化
firebase_admin.initialize_app(
    credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
)

app = Flask(__name__)

# CORSの設定 - 開発環境用
origins = [
    f"http://localhost:{os.getenv('PORT', 8080)}",
]
if int(os.getenv("DEBUG", 0)):
    origins.append("http://localhost:5173")  # DEBUGモードの場合

CORS(
    app,
    origins=origins,
    supports_credentials=False,
    expose_headers=["Authorization"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    methods=["GET", "POST", "OPTIONS"],
)

def process_uploaded_image(image_data: str) -> str:
    """
    アップロードされた画像データをリサイズおよび圧縮し、
    適切な「data:image/～;base64,」形式の文字列を返す関数。
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
        logger.info("元の画像サイズ: %dx%dpx, 容量: %.1fKB", width, height, len(image_bytes)/1024)
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
        logger.info("圧縮後の容量: %.1fKB (quality=%d)", len(output_data)/1024, quality)
        while len(output_data) > MAX_IMAGE_SIZE and quality > 30:
            quality -= 10
            output = io.BytesIO()
            image.save(output, format=output_format, quality=quality, optimize=True)
            output_data = output.getvalue()
            logger.info("再圧縮後の容量: %.1fKB (quality=%d)", len(output_data)/1024, quality)
        processed_base64 = base64.b64encode(output_data).decode("utf-8")
        return f"data:{mime_type};base64,{processed_base64}"
    except Exception as e:
        logger.error("画像処理エラー: %s", str(e), exc_info=True)
        return image_data

def get_api_key_for_model(model: str) -> Optional[str]:
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, "")

def common_message_function(*, model: str, messages: List, stream: bool = False, **kwargs):
    if stream:
        def chat_stream():
            for i, text in enumerate(completion(messages=messages, model=model, stream=True, **kwargs)):
                if not i:
                    yield
                yield text["choices"][0]["delta"].get("content", "") or ""
        cs = chat_stream()
        cs.__next__()
        return cs
    else:
        return completion(messages=messages, model=model, stream=False, **kwargs)["choices"][0]["message"]["content"]

def require_auth(function: Callable) -> Callable:
    @wraps(function)
    def decorated_function(*args, **kwargs) -> Response:
        try:
            auth_header: Optional[str] = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.warning("トークンが見つかりません")
                return jsonify({"error": "認証が必要です"}), 401
            token: str = auth_header.split("Bearer ")[1]
            decoded_token: Dict = auth.verify_id_token(token, clock_skew_seconds=60)
            response: Response = function(decoded_token, *args, **kwargs)
            return response
        except Exception as e:
            logger.error("認証エラー: %s", str(e), exc_info=True)
            response: Response = make_response(jsonify({"error": str(e)}))
            response.status_code = 401
            return response
    return decorated_function

# ======= 各種エンドポイント =======

@app.route("/backend/models", methods=["GET"])
@require_auth
def get_models(decoded_token: Dict) -> Response:
    try:
        logger.info("モデル一覧取得処理を開始")
        raw_models = os.getenv("MODELS", "")
        logger.info(f"環境変数 MODELS の値: {raw_models}")
        model_list = [m.strip() for m in raw_models.split(",") if m.strip()]
        logger.info(f"モデル一覧: {model_list}")
        response: Response = make_response(jsonify({"models": model_list}))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error(f"モデル一覧取得中にエラーが発生しました: {e}", exc_info=True)
        error_response: Response = make_response(jsonify({"error": str(e)}))
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
        response: Response = make_response(jsonify(response_data))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        response: Response = make_response(jsonify({"error": str(e)}))
        response.status_code = 401
        return response

@app.route("/backend/chat", methods=["POST"])
@require_auth
def chat(decoded_token: Dict) -> Response:
    logger.info("チャットリクエストを処理中")
    try:
        data = request.json
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
                logger.info(f"画像の数: {len(msg['images'])}")
                images_to_process = msg["images"][:MAX_IMAGES]
                for image in images_to_process:
                    processed_image = process_uploaded_image(image)
                    parts.append({"type": "image_url", "image_url": {"url": processed_image}})
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
        logger.error(f"チャットエラー: {e}", exc_info=True)
        error_response = make_response(jsonify({"status": "error", "message": str(e)}))
        error_response.status_code = 500
        return error_response

@app.route("/backend/logout", methods=["POST"])
def logout() -> Response:
    try:
        logger.info("ログアウト処理開始")
        response: Response = make_response(
            jsonify({"status": "success", "message": "ログアウトに成功しました"})
        )
        return response, 200
    except Exception as e:
        logger.error("ログアウト処理中にエラーが発生: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 401

# ======= 詳細なジオコーディング結果を返すエンドポイント =======
@app.route("/backend/query2coordinates", methods=["POST"])
@require_auth
def query2coordinates(decoded_token: Dict) -> Response:
    """
    フロントエンドから送られてきた各行（クエリー）を用いてジオコーディングを行い、
    Maps API の詳細なレスポンス情報を含む JSON を返却するエンドポイント
    """
    try:
        data = request.get_json() or {}
        lines = data.get("lines", [])
        logger.info("受信したクエリーリスト: %s", lines)
        
        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not google_maps_api_key:
            raise Exception("Google Maps APIキーが設定されていません")
        
        results = []
        for line in lines:
            query = line.strip()
            if not query:
                continue
            geocode_data = get_coordinates(google_maps_api_key, query)
            if geocode_data.get("status") == "OK" and geocode_data.get("results"):
                result = geocode_data["results"][0]
                location = result["geometry"]["location"]
                results.append({
                    "query": query,
                    "status": geocode_data.get("status"),
                    "formatted_address": result.get("formatted_address", ""),
                    "latitude": location.get("lat"),
                    "longitude": location.get("lng"),
                    "location_type": result["geometry"].get("location_type", ""),
                    "place_id": result.get("place_id", ""),
                    "types": ", ".join(result.get("types", [])),
                    "error": ""
                })
            else:
                results.append({
                    "query": query,
                    "status": geocode_data.get("status", "エラー"),
                    "formatted_address": "",
                    "latitude": None,
                    "longitude": None,
                    "location_type": "",
                    "place_id": "",
                    "types": "",
                    "error": geocode_data.get("status", "エラー")
                })
        
        response: Response = make_response(jsonify({"status": "success", "results": results}))
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("ジオコーディング処理エラー: %s", str(e), exc_info=True)
        error_response = make_response(jsonify({"error": str(e)}))
        error_response.status_code = 500
        return error_response

# ======= フロントエンド配信用（DEBUG以外） =======
if not int(os.getenv("DEBUG", 0)):
    FRONTEND_PATH = "./frontend/dist"
    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_PATH, "index.html")
    @app.route("/<path:path>")
    def static_file(path):
        return send_from_directory(FRONTEND_PATH, path)

# %%
if __name__ == "__main__":
    logger.info("Flaskアプリを起動します DEBUG: %s", bool(int(os.getenv("DEBUG", 0))))
    app.run(port=int(os.getenv("PORT", "8080")), debug=bool(int(os.getenv("DEBUG", 0))))
# %%
google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
query = "東京駅"
geocode_data = get_coordinates(google_maps_api_key, query)
# %%
