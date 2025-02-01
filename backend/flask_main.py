from flask import Flask, request, Response, jsonify, make_response
from flask_cors import CORS
from firebase_admin import auth, credentials
from dotenv import load_dotenv
from functools import wraps
import os, json, logging, firebase_admin
from PIL import Image
from typing import Dict, Union, Optional, Tuple, Callable, Any, List
from litellm import completion, token_counter

# .envファイルを読み込み
load_dotenv('./config/.env')

# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

# Firebase Admin SDKの初期化
# ここで環境変数から認証ファイルパスを取得し、Firebaseアプリを初期化しています
cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
firebase_admin.initialize_app(cred)

app = Flask(__name__)
# CORSの設定 - 開発環境用
CORS(
    app,
    origins=["http://localhost:5173"],
    supports_credentials=True,
    expose_headers=["Authorization"],
    allow_headers=["Content-Type", "Authorization"],
)

def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からソース名を抽出してAPIキーを取得"""
    source = model.split('/')[0] if '/' in model else model
    return json.loads(os.getenv("MODEL_API_KEYS", "{}")).get(source, '')

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
            response : Response = function(decoded_token, *args, **kwargs)

            return response
        except Exception as e:
            logger.error("認証エラー: %s", str(e), exc_info=True)
            response : Response = make_response(jsonify({"error": str(e)}))
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

        response : Response = make_response(jsonify({"models": model_list}))
        response.status_code = 200
        return response

    except Exception as e:
        logger.error(f"モデル一覧取得中にエラーが発生しました: {e}", exc_info=True)
        error_response : Response = make_response(jsonify({"error": str(e)}))
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
        }
        logger.info("認証検証完了")
        renponse : Response = make_response(jsonify(response_data))
        renponse.status_code = 200
        return renponse
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        response : Response = make_response(jsonify({"error": str(e)}))
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
        error_keyword = "trigger_error"  # 例：このキーワードが含まれるとエラー発生
        for msg in messages:
            content = msg.get("content", "")
            #logger.debug('メッセージの内容: %s', content)
            if error_keyword == content:
                raise ValueError("不正なキーワードが含まれています")

        # 送信される各メッセージをLiteLLM向けの形式に変換する
        transformed_messages = []
        for msg in messages:
            # ユーザーのメッセージで、画像がアップロードされている場合
            if msg.get("role") == "user" and msg.get("images"):
                parts = []
                # テキスト部分がある場合、"text"オブジェクトとして追加
                if msg.get("content"):
                    parts.append({
                        "type": "text",
                        "text": msg["content"]
                    })
                # 各画像について、"image_base64"として追加
                for image in msg["images"]:
                    parts.append({
                        "type": "image_base64",
                        "base64": image
                    })
                # 変換後の内容を設定し、不要な"images"フィールドは削除
                msg["content"] = parts
                msg.pop("images", None)
            transformed_messages.append(msg)
        
        logger.info(f"変換後のmessages: {transformed_messages}")

        # 選択されたモデルを使用してチャット応答を生成
        logger.info(f"選択されたモデル: {model}")
        logger.info(f"messages: {transformed_messages}")

        response = Response(
            common_message_function(
                model=model, stream=True, messages=transformed_messages,
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







if __name__ == "__main__":
    # Flaskアプリ起動時のログを出力
    logger.info("Flaskアプリを起動します")
    app.run(
        port=int(os.getenv("PORT", "8080")), debug=bool(os.getenv("DEBUG", "False"))
    )

