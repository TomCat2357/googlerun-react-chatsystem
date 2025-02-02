#%%
from flask import Flask, request, Response, jsonify, make_response, send_from_directory
from flask_cors import CORS
from firebase_admin import auth, credentials
from dotenv import load_dotenv
from functools import wraps
import os, json, logging, firebase_admin, io, base64
from PIL import Image
from typing import Dict, Union, Optional, Tuple, Callable, Any, List
from litellm import completion, token_counter


# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

# .envファイルを読み込み
load_dotenv("./config/.env")

# 環境変数から画像処理設定を読み込む
MAX_IMAGES = int(os.getenv("MAX_IMAGES", "5"))
MAX_LONG_EDGE = int(os.getenv("MAX_LONG_EDGE", "1568"))
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE", "5242880"))  # デフォルト5MB

# Firebase Admin SDKの初期化
# ここで環境変数から認証ファイルパスを取得し、Firebaseアプリを初期化しています
cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
firebase_admin.initialize_app(cred)


app = Flask(__name__)
# CORSの設定 - 開発環境用
CORS(
    app,
    origins=["http://localhost:5173", "http://localhost:5000"],
    supports_credentials=True,
    expose_headers=["Authorization"],
    allow_headers=["Content-Type", "Authorization"],
)



def process_uploaded_image(image_data: str) -> str:
    """
    アップロードされた画像データをリサイズおよび圧縮し、
    適切な「data:image/～;base64,」形式の文字列を返す関数。
    """

    try:
        # data:～のヘッダーがある場合は除去
        header = None
        if image_data.startswith("data:"):
            header, image_data = image_data.split(",", 1)

        # base64デコードして画像読み込み
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))

        # 画像のモードがRGBまたはRGBAでない場合は変換
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")

        width, height = image.size
        logger.info(
            "元の画像サイズ: %dx%dpx, 容量: %.1fKB",
            width,
            height,
            len(image_bytes) / 1024,
        )

        # 長辺が1568ピクセルを超えている場合はリサイズ（アスペクト比維持）
        if max(width, height) > MAX_LONG_EDGE:
            scale = MAX_LONG_EDGE / max(width, height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info("リサイズ後: %dx%dpx", new_width, new_height)

        # 初期の品質設定
        quality = 85
        output = io.BytesIO()
        # 出力フォーマットとMIMEタイプを決定
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

        # 5MBを超える場合、品質を下げて再圧縮（最小品質は30まで）
        while len(output_data) > MAX_IMAGE_SIZE and quality > 30:
            quality -= 10
            output = io.BytesIO()
            image.save(output, format=output_format, quality=quality, optimize=True)
            output_data = output.getvalue()
            logger.info(
                "再圧縮後の容量: %.1fKB (quality=%d)", len(output_data) / 1024, quality
            )

        processed_base64 = base64.b64encode(output_data).decode("utf-8")
        # 画像の形式に合わせたMIMEタイプを設定して返却する
        return f"data:{mime_type};base64,{processed_base64}"
    except Exception as e:
        logger.error("画像処理エラー: %s", str(e), exc_info=True)
        # エラー時は元の画像データを返す
        return image_data


def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からソース名を抽出してAPIキーを取得"""
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
                # 先行して実行することでいち早くエラーを引き起こさせる。
                if not i:
                    yield
                yield text["choices"][0]["delta"].get("content", "") or ""

        cs = chat_stream()
        # これでif not i: yieldの処理を行わせる。そのためにはcompletionの処理が実行されて、エラーが起きるとしたらここで起きる。
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

            # トークンを取得
            token: str = auth_header.split("Bearer ")[1]

            # Firebaseでトークン検証
            decoded_token: Dict = auth.verify_id_token(token, clock_skew_seconds=60)

            # デコレートされた関数にトークン情報を渡す
            response: Response = function(decoded_token, *args, **kwargs)

            return response
        except Exception as e:
            logger.error("認証エラー: %s", str(e), exc_info=True)
            response: Response = make_response(jsonify({"error": str(e)}))
            response.status_code = 401
            return response

    return decorated_function


@app.route("/app/models", methods=["GET"])
@require_auth
def get_models(decoded_token: Dict) -> Response:
    """
    環境変数 MODELS に記載されているモデル一覧を返すエンドポイント
    """
    try:
        logger.info("モデル一覧取得処理を開始")
        raw_models = os.getenv("MODELS", "")
        logger.info(f"環境変数 MODELS の値: {raw_models}")
        # MODELS をカンマ区切りで分割し、strip() で前後空白を除去
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


@app.route("/app/verify-auth", methods=["GET"])
@require_auth
def verify_auth(decoded_token: Dict) -> Tuple[Response, int]:
    """
    認証トークンを検証するエンドポイント

    Returns:
        Response: 認証結果を含むレスポンス
    """
    try:
        logger.info("認証検証開始")
        logger.info("トークンの復号化成功。ユーザー: %s", decoded_token.get("email"))

        response_data: Dict[str, Union[str, Dict]] = {
            "status": "success",
            "user": {
                "email": decoded_token.get("email"),
                "uid": decoded_token.get("uid"),
            },
            "expire_time": decoded_token.get("exp"),
        }
        logger.info("認証検証完了")
        renponse: Response = make_response(jsonify(response_data))
        renponse.status_code = 200
        return renponse
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        response: Response = make_response(jsonify({"error": str(e)}))
        response.status_code = 401
        return response


@app.route("/app/chat", methods=["POST"])
@require_auth
def chat(decoded_token: Dict) -> Response:
    """チャットエンドポイント"""
    logger.info("チャットリクエストを処理中")
    try:
        data = request.json
        messages = data.get("messages", [])
        model = data.get("model")  # モデル情報を取得。デフォルト値を設定
        logger.info(f"モデル: {model}")
        if model is None:
            raise ValueError("モデル情報が提供されていません")
        model_api_key = get_api_key_for_model(model)

        # ここで特定のキーワードをチェックする
        error_keyword = "@trigger_error"  # 例：このキーワードが含まれるとエラー発生
        error_flag = False
        for msg in messages:
            content = msg.get("content", "")
            # logger.debug('メッセージの内容: %s', content)
            if error_keyword == content:
                error_flag = True
                break

        # 送信される各メッセージをLiteLLM向けの形式に変換する
        transformed_messages = []
        for msg in messages:
            # ユーザーのメッセージで、画像がアップロードされている場合
            if msg.get("role") == "user" and msg.get("images"):
                parts = []
                if msg.get("content"):
                    parts.append({"type": "text", "text": msg["content"]})
                # １ターンあたり最大MAX_IMAGES（５ぐらい？）枚の画像まで
                logger.info(f"画像の数: {len(msg['images'])}")
                images_to_process = msg["images"][:MAX_IMAGES]

                for image in images_to_process:
                    processed_image = process_uploaded_image(image)
                    # image_base64 ではなく image_url を使い、内部に url キーを設定する
                    parts.append(
                        {"type": "image_url", "image_url": {"url": processed_image}}
                    )
                msg["content"] = parts
                msg.pop("images", None)

            transformed_messages.append(msg)

        # 選択されたモデルを使用してチャット応答を生成
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


@app.route("/app/logout", methods=["POST"])
def logout() -> Response:
    """
    ログアウト処理を行うエンドポイント

    Returns:
        Response: ログアウト結果を含むレスポンス
    """
    try:
        logger.info("ログアウト処理開始")
        response: Response = make_response(
            jsonify({"status": "success", "message": "ログアウトに成功しました"})
        )
        return response, 200
    except Exception as e:
        logger.error("ログアウト処理中にエラーが発生: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 401
    

BASE_PATH = '../frontend/dist'

@app.route('/')
def index():
    return send_from_directory(BASE_PATH, 'index.html')

@app.route('/<path:path>')
def static_file(path):
    return send_from_directory(BASE_PATH, path)


#%%
if __name__ == "__main__":
    # Flaskアプリ起動時のログを出力
    logger.info("Flaskアプリを起動します")
    app.run(
        port=int(os.getenv("PORT", "8080")), debug=bool(os.getenv("DEBUG", 0))
    )
