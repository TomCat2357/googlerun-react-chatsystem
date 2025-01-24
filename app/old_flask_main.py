# %%
import os
import logging
from flask import (
    Flask,
    request,
    make_response,
    jsonify,
    redirect,
    Response,
    render_template,
    Request,
)
from flask_cors import CORS
from firebase_admin import credentials, auth, initialize_app
from functools import wraps
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Union, List, Tuple, Callable, TypeVar, cast
import ollama, json
import ipaddress
from litellm import completion, token_counter

# %%
# ロギングの設定
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

logger.info("アプリケーションの初期化を開始...")

# 環境変数の読み込み
load_dotenv('./config/.env')
logger.info("環境変数を読み込みました")

# Flaskアプリケーションの初期化
app: Flask = Flask(__name__)
app.config["API_GATEWAY_KEY"] = os.getenv("API_GATEWAY_KEY", "")
CORS(app)

# モデルのAPIキーを読み込む
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


def is_ip_allowed(client_ip: str, allowed_networks: List[str]) -> bool:
    """
    IPアドレスの許可判定を行う
    1. CIDR表記で.0で終わる場合 → ネットワーク範囲内判定
    2. それ以外 → 完全一致判定（/8などの表記は無視）
    """
    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
        for network in allowed_networks:
            network = network.strip()

            # CIDR表記で、かつネットワークアドレスが.0で終わる場合は範囲判定
            if "/" in network and network.split("/")[0].strip().endswith(".0"):
                try:
                    if client_ip_obj in ipaddress.ip_network(network):
                        return True
                except ValueError:
                    logger.warning(f"Invalid CIDR format: {network}")
                    continue
            else:
                # CIDR表記でない、または.0で終わらない場合は
                # /8などの表記を取り除いて単一IPとして判定
                compare_ip = network.split("/")[0].strip()
                if str(client_ip_obj) == compare_ip:
                    return True

        return False
    except ValueError:
        logger.error(f"Invalid IP address: {client_ip}")
        return False


def init_firebase_config() -> Dict[str, str]:
    """Firebase設定を取得する関数"""
    logger.debug("Firebase設定を取得中")

    firebase_api_key: str = os.getenv("FIREBASE_API_KEY", "")
    firebase_auth_domain: str = os.getenv("FIREBASE_AUTH_DOMAIN", "")

    if not firebase_api_key or not firebase_auth_domain:
        error_msg: str = "必要な環境変数が不足しています:"
        if not firebase_api_key:
            error_msg += " FIREBASE_API_KEY"
        if not firebase_auth_domain:
            error_msg += " FIREBASE_AUTH_DOMAIN"
        logger.error(error_msg)
        raise ValueError(error_msg)

    return {"apiKey": firebase_api_key, "authDomain": firebase_auth_domain}


# アプリケーション設定を初期化
app.config["FIREBASE_CONFIG"] = init_firebase_config()
logger.info("FlaskアプリケーションをCORS設定で初期化し、Firebase設定を読み込みました")

# Firebase Admin SDKの初期化
try:
    logger.info("Firebase Admin SDKの初期化を試みています...")
    initialize_app()
    logger.info("Firebase Admin SDKの初期化に成功しました")
except Exception as e:
    logger.error(f"Firebaseの初期化に失敗しました: {e}", exc_info=True)
    raise


def set_auth_cookie(response: Response, token: str) -> None:
    """セキュアなHTTPOnlyクッキーを設定する関数"""
    logger.debug("認証クッキーを設定中")
    expires: datetime = datetime.now() + timedelta(hours=1)
    response.set_cookie(
        "session_token",
        token,
        httponly=True,
        secure=True,
        samesite="Lax",
        expires=expires,
        path="/",
    )


def verify_token(
    request: Request,
) -> Tuple[
    Optional[Dict[str, Any]], Optional[Response], Optional[int], bool, Optional[str]
]:
    """トークン検証を行う関数"""
    logger.debug("トークン検証を開始")

    auth_header: Optional[str] = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        is_bearer_token: bool = True
        logger.debug("Authorizationヘッダーを検出")
        token: str = auth_header.split("Bearer ")[1]
    else:
        is_bearer_token = False
        token = request.cookies.get("session_token")
        if token:
            logger.debug("クッキーからトークンを検出")
            try:
                decoded_token: Dict[str, Any] = auth.verify_id_token(
                    token, check_revoked=False
                )
                exp_timestamp: float = float(decoded_token.get("exp", 0))
                current_timestamp: float = datetime.now().timestamp()
                remaining_time: float = exp_timestamp - current_timestamp
                remaining_minutes: float = remaining_time / 60
                logger.debug(f"クッキートークンの残り時間: {remaining_minutes:.2f}分")
            except Exception as e:
                logger.debug(f"クッキートークンの有効期限確認中にエラー: {e}")
        else:
            logger.warning("トークンが提供されていません")
            error_response = make_response(jsonify({"error": "トークンがありません"}))
            error_response.status_code = 401
            return None, error_response, 401, False, None

    try:
        logger.debug("Firebaseでトークンを検証中")
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        logger.info("トークン検証に成功")
        return decoded_token, None, None, is_bearer_token, token
    except auth.ExpiredIdTokenError:
        logger.warning("トークンの有効期限切れ")
        error_response = make_response(jsonify({"error": "トークンの有効期限切れ"}))
        error_response.status_code = 401
        return None, error_response, 401, False, None
    except Exception as e:
        logger.error(f"トークン検証に失敗: {e}", exc_info=True)
        error_response = make_response(jsonify({"error": "無効なトークンです"}))
        error_response.status_code = 401
        return None, error_response, 401, False, None


def get_cors_headers() -> Dict[str, str]:
    """CORSヘッダーを生成する関数"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
        "Access-Control-Max-Age": "3600",
    }


F = TypeVar("F", bound=Callable[..., Any])


def require_auth(f: F) -> F:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        logger.info(f"認証チェックを開始: エンドポイント {request.path}")

        auth_result: Tuple[
            Optional[Dict[str, Any]],
            Optional[Response],
            Optional[int],
            bool,
            Optional[str],
        ] = verify_token(request)
        user, error_response, error_code, is_bearer_token, token = auth_result

        if error_response:
            logger.warning(
                f"認証失敗: {error_response.json if hasattr(error_response, 'json') else error_response}"
            )

            if isinstance(error_response.json, dict) and error_response.json.get(
                "error"
            ) in ["トークンがありません", "無効なトークンです", "トークンの有効期限切れ"]:
                logger.info("認証失敗によりログインページにリダイレクトします")
                response = make_response(redirect("/"))
                headers = get_cors_headers()
                for key, value in headers.items():
                    response.headers[key] = value
                return response

            return error_response

        logger.info("認証成功")
        response = f(user, *args, **kwargs)
        if "logout" not in request.path and is_bearer_token and token:
            logger.info("クッキーセット")
            set_auth_cookie(response, token)
        return response

    return cast(F, decorated_function)


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "OPTIONS"])
def router(path):
    """統合ルーティングハンドラ"""

    client_ip = request.remote_addr
    if request.headers.get("X-Forwarded-For"):
        client_ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()

    logger.info(
        f"リクエストパス: {path}, メソッド: {request.method}, クライアントIP: {client_ip}"
    )
    allowed_networks = os.getenv("ALLOWED_NETWORKS").split(",")

    if not is_ip_allowed(client_ip, allowed_networks):
        logger.warning(f"Forbidden access attempt from IP: {client_ip}")
        return (
            render_template(
                "error.html",
                error_code=403,
                error_title="Forbidden",
                error_message="アクセスが制限されています",
                client_ip=client_ip,
            ),
            403,
        )
    if path == "app/chat" and request.method == "POST":
        return chat()

    # ヘルスチェック
    if path == "health":
        return health_check()

    # ファビコン
    if path == "favicon.ico":
        response = make_response("")
        response.status_code = 204
        return response

    # ログインページ
    if path == "":
        return login()

    # メインUI
    if path == "app/main_ui":
        return main_ui()

    # ログアウト
    if path == "app/logout" and request.method == "POST":
        return logout()

    # トークンリフレッシュ
    if path == "app/refresh-token" and request.method == "POST":
        return refresh_token()

    # 404エラー
    return make_response(jsonify({"error": "Not Found"}), 404)


def login() -> Response:
    """ログインページを表示する処理"""
    logger.info("ログインページのリクエストを処理中")
    try:
        redirect_url = request.args.get("redirect_url", "/app/main_ui")
        logger.debug(f"リダイレクト先URL: {redirect_url}")

        if not redirect_url.startswith("/app/"):
            logger.warning(f"無効なredirect_url: {redirect_url}")
            redirect_url = "/app/main_ui"

        return render_template(
            "login.html",
            firebase_config=app.config["FIREBASE_CONFIG"],
            redirect_url=redirect_url,
            API_GATEWAY_KEY=app.config["API_GATEWAY_KEY"],
        )

    except ValueError as e:
        logger.error(f"ログインページでエラー発生: {e}", exc_info=True)
        error_response = make_response(jsonify({"error": str(e)}))
        error_response.status_code = 500
        return error_response


@require_auth
def main_ui(user: Dict[str, Any]) -> Response:
    """メインUI画面の表示処理"""
    logger.info("メインUIのリクエストを処理中")
    try:
        user_email = user.get("email", "Unknown User")
        models = os.getenv("MODELS")
        logger.debug(f"モデル: {models}")
        if models is None:
            raise Exception("MODELS環境変数が設定されていません")
        return render_template(
            "main.html",
            firebase_config=app.config["FIREBASE_CONFIG"],
            user_email=user_email,
            API_GATEWAY_KEY=app.config["API_GATEWAY_KEY"],
            models=models,
        )
    except Exception as e:
        logger.error(f"メインUI表示中にエラーが発生: {str(e)}")
        return Response("エラーが発生しました", status=500)


@require_auth
def logout(user: Dict[str, Any]) -> Response:
    """ログアウト処理"""
    logger.info("ログアウトリクエストを処理中")
    try:
        response = make_response(
            jsonify({"status": "success", "message": "ログアウト成功"})
        )

        response.delete_cookie("session_token", path="/")
        response.delete_cookie("session_token", path="/app")
        response.delete_cookie("session_token", domain=request.host)
        if ":" in request.host:
            response.delete_cookie("session_token", domain=request.host.split(":")[0])

        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate, private"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        response.headers.update(get_cors_headers())
        logger.info("ログアウト成功")
        return response

    except Exception as e:
        logger.error(f"ログアウトエラー: {e}", exc_info=True)
        error_response = make_response(
            jsonify({"error": "ログアウトエラー", "details": str(e)})
        )
        error_response.status_code = 500
        return error_response


@require_auth
def refresh_token(user: Dict[str, Any], *args: Any) -> Response:
    """トークンリフレッシュ処理"""
    logger.info("トークンリフレッシュリクエストを処理中")
    try:
        auth_header: Optional[str] = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise ValueError("新しいトークンが提供されていません")

        new_token: str = auth_header.split("Bearer ")[1]
        decoded_token: Dict[str, Any] = auth.verify_id_token(
            new_token, clock_skew_seconds=60
        )

        response = make_response(
            jsonify(
                {
                    "status": "success",
                    "message": "トークンを更新しました",
                    "token_expiration": decoded_token.get("exp"),
                }
            )
        )

        set_auth_cookie(response, new_token)
        response.headers.update(get_cors_headers())
        logger.info("トークンの更新に成功しました")
        return response

    except ValueError as e:
        logger.error(f"トークンリフレッシュエラー - 不正な入力: {e}")
        error_response = make_response(jsonify({"error": str(e)}))
        error_response.status_code = 400
        return error_response

    except Exception as e:
        logger.error(f"トークンリフレッシュエラー: {e}", exc_info=True)
        error_response = make_response(
            jsonify({"error": "トークンリフレッシュに失敗しました"})
        )
        error_response.status_code = 500
        return error_response


@require_auth
def chat(user: Dict[str, Any]) -> Response:
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
        
        # 選択されたモデルを使用してチャット応答を生成
        logger.info(f"選択されたモデル: {model}")
        logger.info(f"messages: {messages}")

        return Response(
            common_message_function(
                # 取得したモデルを渡す
                model=model, stream=True, messages=messages,
                api_key=model_api_key,
                
            ),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "Transfer-Encoding": "chunked"},
        )

    except Exception as e:
        logger.error(f"チャットエラー: {e}", exc_info=True)
        error_response = make_response(jsonify({"status": "error", "message": str(e)}))
        error_response.status_code = 500
        return error_response


@require_auth
def health_check() -> Tuple[Response, int]:
    """システムの健全性チェック"""
    try:
        firebase_config: Dict[str, str] = app.config["FIREBASE_CONFIG"]
        response = make_response(
            jsonify({"status": "healthy", "firebase_configured": bool(firebase_config)})
        )
        return response, 200
    except Exception as e:
        error_response = make_response(
            jsonify({"status": "unhealthy", "error": str(e)})
        )
        return error_response, 500


@app.after_request
def after_request(response: Response) -> Response:
    """全てのレスポンスにCORSヘッダーを追加"""
    logger.debug(f"レスポンスにCORSヘッダーを追加: パス {request.path}")
    response.headers.update(get_cors_headers())
    return response


@app.errorhandler(Exception)
def handle_error(error: Exception) -> Tuple[Response, int]:
    """エラーハンドラー"""
    logger.error(f"未処理のエラーが発生: {error}", exc_info=True)
    error_response = make_response(
        jsonify({"error": "システムエラー", "details": str(error)})
    )
    return error_response, 500


# %%
if __name__ == "__main__":
    logger.info("Flask開発サーバーを起動中...")
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        debug=bool(os.getenv("DEBUG", False)),
    )
