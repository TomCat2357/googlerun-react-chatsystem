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
from backend.utils.speech2text import transcribe_streaming_v2

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
        logger.error(f"チャットエラー: {e}", exc_info=True)
        error_response = make_response(jsonify({"status": "error", "message": str(e)}))
        error_response.status_code = 500
        return error_response


@app.route("/backend/address2coordinates", methods=["POST"])
@require_auth
def query2coordinates(decoded_token: Dict) -> Response:
    """
    フロントエンドから送られてきた各行（クエリー）を用いてジオコーディングを行い、
    Maps API の詳細なレスポンス情報を含む JSON を返却するエンドポイント。
    ※ 同一のクエリーは１回の API 呼び出しで処理し、その結果を全ての出現箇所に展開します。
    """
    try:
        data = request.get_json() or {}
        lines = data.get("lines", [])
        logger.info("受信したクエリーリスト: %s", lines)

        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not google_maps_api_key:
            raise Exception("Google Maps APIキーが設定されていません")

        # まず、同一クエリーを除外するために一意なクエリーを抽出
        unique_queries = {}
        for line in lines:
            query = line.strip()
            if not query:
                continue
            if query not in unique_queries:
                unique_queries[query] = None

        # 各一意なクエリーについて、1回だけ API を呼び出す
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

        # 元の各行に対して、対応する結果を付与する（重複行も同じ結果となる）
        results = []
        for line in lines:
            query = line.strip()
            if not query:
                continue
            results.append(unique_queries[query])

        response: Response = make_response(
            jsonify({"status": "success", "results": results})
        )
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
    """
    フロントエンドから送られてきた各行（緯度,経度）を用いてリバースジオコーディングを行い、
    Maps API の詳細なレスポンス情報を含む JSON を返却するエンドポイント。
    """
    try:
        data = request.get_json() or {}
        lines = data.get("lines", [])
        logger.info("受信した緯度経度リスト: %s", lines)
        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not google_maps_api_key:
            raise Exception("Google Maps APIキーが設定されていません")

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
        response: Response = make_response(
            jsonify({"status": "success", "results": results})
        )
        response.status_code = 200
        return response
    except Exception as e:
        logger.error("リバースジオコーディング処理エラー: %s", str(e), exc_info=True)
        error_response = make_response(jsonify({"error": str(e)}))
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


@app.route("/backend/static-map", methods=["GET"])
@require_auth
def get_static_map_image(decoded_token: Dict) -> Response:
    """
    指定された緯度経度の静的地図（衛星写真）を取得するエンドポイント
    """
    try:
        latitude = float(request.args.get("latitude"))
        longitude = float(request.args.get("longitude"))
        zoom = int(request.args.get("zoom", 18))
        width = int(request.args.get("width", 600))
        height = int(request.args.get("height", 600))
        map_type = request.args.get("maptype", "satellite")

        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not google_maps_api_key:
            raise Exception("Google Maps APIキーが設定されていません")

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
    """
    指定された緯度経度のストリートビュー画像を取得するエンドポイント
    """
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

        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not google_maps_api_key:
            raise Exception("Google Maps APIキーが設定されていません")

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


@app.route("/backend/speech2text", methods=["POST"])
@require_auth
def speech2text(decoded_token: dict) -> Response:
    try:
        data = request.get_json() or {}
        audio_data = data.get("audio_data", "")
        if not audio_data:
            raise ValueError("音声データが提供されていません")

        # "data:audio/～;base64,..."形式の場合はヘッダー部分を除去
        if audio_data.startswith("data:"):
            _, audio_data = audio_data.split(",", 1)

        # base64デコードしてバイト列に変換
        audio_bytes = base64.b64decode(audio_data)

        # 音声文字起こしを実行（日本語認識の場合）
        responses = transcribe_streaming_v2(audio_bytes, language_codes=["ja-JP"])

        full_transcript = ""
        timed_transcription = []

        # 修正：datetime.timedeltaオブジェクトに対応するため total_seconds() を使用
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
                    # 修正：start_offset/end_offset を利用
                    start_time = format_time(alternative.words[0].start_offset)
                    end_time = format_time(alternative.words[-1].end_offset)
                    timed_transcription.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": alternative.transcript
                    })

        return jsonify({
            "transcription": full_transcript,
            "timed_transcription": timed_transcription
        })
    except Exception as e:
        logger.error(f"音声文字起こしエラー: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500




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
