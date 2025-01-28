from flask import Flask, request, Response, jsonify, make_response
from flask_cors import CORS
import firebase_admin
from firebase_admin import auth, credentials
import logging
from dotenv import load_dotenv
from functools import wraps
import os
from typing import Dict, Union, Optional, Tuple, Callable, Any

# .envファイルを読み込み
load_dotenv()

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
            response: Tuple[Response, int] = function(decoded_token, *args, **kwargs)

            return response

        except Exception as e:
            logger.error("認証エラー: %s", str(e), exc_info=True)
            return jsonify({"error": str(e)}), 401

    return decorated_function


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

        response: Response = make_response(jsonify(response_data))
        logger.info("認証成功。正常なレスポンスを送信")
        return response, 200

    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 401


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
