# utils/common.py
import logging
import os
import base64
import io
import ipaddress
import time
import json
from PIL import Image
from google.cloud import secretmanager
from firebase_admin import auth, credentials
from typing import Dict, Optional, Any, List, Callable
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse  # StreamingResponseをインポート
from starlette.middleware.base import BaseHTTPMiddleware
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

# ログ設定
LOG_MAX_BODY_SIZE = int(os.getenv("LOG_MAX_BODY_SIZE", "10240"))  # ログに記録する最大ボディサイズ（デフォルト10KB）
LOG_MAX_TEXT_LENGTH = int(os.getenv("LOG_MAX_TEXT_LENGTH", "1000"))  # テキストログの最大長さ（デフォルト1000文字）

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
        logger.info(f"@リクエスト送信元IP: {client_ip}")
    except ValueError:
        time.sleep(0.05)
        raise HTTPException(status_code=400, detail="不正なIPアドレス形式です")

    # ALLOWED_IPSは.envから取得する設定とする
    allowed_tokens = ALLOWED_IPS
    logger.info(f'許可されたIPアドレスまたはネットワーク: {allowed_tokens}')
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


# =====以下、リクエスト・レスポンスログ取得のための追加クラスと関数=====

class RequestResponseLoggerMiddleware(BaseHTTPMiddleware):
    """リクエストとレスポンスの詳細をログに記録するミドルウェア"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # リクエスト時間を記録
        start_time = time.time()
        
        # リクエスト情報をログに記録（簡略化可能）
        await self.log_request(request)
        
        try:
            # 実際のリクエスト処理
            response = await call_next(request)
            
            # 処理時間の計算
            process_time = time.time() - start_time
            
            # StreamingResponseの場合は特別処理
            if isinstance(response, StreamingResponse):
                # 最小限のログのみ記録
                logger.info(
                    f"StreamingResponse: status={response.status_code}, "
                    f"type={response.media_type}, time={round(process_time * 1000, 2)}ms"
                )
            else:
                # 通常のレスポンスはフル記録
                self.log_response(response, process_time)
            
            # 処理時間をレスポンスヘッダーに追加
            response.headers["X-Process-Time"] = str(round(process_time, 6))
            
            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"エラー: {str(e)}, 時間: {round(process_time * 1000, 2)}ms", exc_info=True)
            raise
    
    async def get_request_body_copy(self, request: Request) -> Optional[bytes]:
        """リクエストボディのコピーを取得し、リクエストを再利用可能にする"""
        if request.method not in ["POST", "PUT", "PATCH"]:
            return None
        
        try:
            # ボディを読み取る
            body_bytes = await request.body()
            
            # ボディを再度使用できるようにリクエストを再設定
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            request._receive = receive
            
            return body_bytes
        except Exception as e:
            logger.warning(f"リクエストボディコピー取得エラー: {str(e)}")
            return None
    
    async def log_request(self, request: Request):
        """リクエスト情報をログに記録する"""
        try:
            # クライアントIP取得
            client_ip = request.headers.get("x-forwarded-for", "")
            if not client_ip:
                client_ip = request.client.host if request.client else "unknown"
            if client_ip and "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()
            
            # リクエストヘッダー（機密情報をマスク）
            headers = dict(request.headers)
            masked_headers = self._mask_sensitive_headers(headers)
            
            # リクエストURI情報
            path = request.url.path
            query_params = dict(request.query_params)
            method = request.method
            
            # リクエストボディ（POSTなどの場合）
            body_info = None
            if method in ["POST", "PUT", "PATCH"]:
                try:
                    body_bytes = await request.body()
                    
                    # ボディを再利用可能にする
                    async def receive():
                        return {"type": "http.request", "body": body_bytes, "more_body": False}
                    request._receive = receive
                    
                    # ボディ内容を表示（サイズが環境変数設定値より大きい場合は省略）
                    if len(body_bytes) > LOG_MAX_BODY_SIZE:
                        body_info = f"<Binary data: {len(body_bytes) / 1024:.2f} KB>"
                    else:
                        try:
                            body_text = body_bytes.decode("utf-8")
                            # JSONかどうか確認
                            try:
                                json_data = json.loads(body_text)
                                body_info = self._mask_sensitive_json(json_data)
                            except:
                                if len(body_text) > LOG_MAX_TEXT_LENGTH:
                                    body_info = body_text[:LOG_MAX_TEXT_LENGTH] + "..."
                                else:
                                    body_info = body_text
                        except:
                            body_info = f"<Binary data: {len(body_bytes)} bytes>"
                except Exception as e:
                    body_info = f"<Error reading body: {str(e)}>"
            
            # リクエスト情報の構築
            request_info = {
                "method": method,
                "path": path,
                "query_params": query_params,
                "client_ip": client_ip,
                "headers": masked_headers
            }
            
            # ボディ情報があれば追加
            if body_info:
                request_info["body"] = body_info
            
            # ログ出力
            logger.info(f"リクエスト受信: {json.dumps(request_info, ensure_ascii=False)}")
        except Exception as e:
            logger.error(f"リクエストログ記録エラー: {str(e)}", exc_info=True)
    
    def log_response(self, response: Response, process_time: float):
        """レスポンス情報をログに記録する"""
        try:
            # レスポンス情報
            response_info = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "process_time_ms": round(process_time * 1000, 2),
                "response_type": response.__class__.__name__
            }
            
            # Content-Lengthが存在するならサイズを記録
            if "content-length" in response.headers:
                size = int(response.headers["content-length"])
                response_info["size"] = f"{round(size / 1024, 2)} KB" if size > 1024 else f"{size} bytes"
            
            # JSONレスポンスの場合、内容をログ記録（サイズに応じて）
            if isinstance(response, JSONResponse) and hasattr(response, "body"):
                try:
                    body_size = len(response.body)
                    if body_size <= LOG_MAX_BODY_SIZE:  # 環境変数設定値以下の場合のみ記録
                        body_text = response.body.decode("utf-8")
                        try:
                            json_data = json.loads(body_text)
                            # 機密情報をマスク
                            response_info["body"] = self._mask_sensitive_json(json_data)
                        except:
                            if len(body_text) > LOG_MAX_TEXT_LENGTH:
                                response_info["body"] = body_text[:LOG_MAX_TEXT_LENGTH] + "..."
                            else:
                                response_info["body"] = body_text
                    else:
                        response_info["body"] = f"<Body size: {body_size / 1024:.2f} KB>"
                except Exception as e:
                    response_info["body_error"] = str(e)
            
            # ログ出力
            logger.info(f"レスポンス送信: {json.dumps(response_info, ensure_ascii=False)}")
        except Exception as e:
            logger.error(f"レスポンスログ記録エラー: {str(e)}", exc_info=True)
    
    def _mask_sensitive_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """機密情報を含むヘッダーをマスクする"""
        sensitive_headers = ["authorization", "cookie", "x-api-key", "api-key"]
        masked_headers = {}
        
        for key, value in headers.items():
            lowercase_key = key.lower()
            if lowercase_key in sensitive_headers:
                if lowercase_key == "authorization" and value.startswith("Bearer "):
                    masked_headers[key] = "Bearer [MASKED]"
                else:
                    masked_headers[key] = "[MASKED]"
            else:
                masked_headers[key] = value
        
        return masked_headers
    
    def _mask_sensitive_json(self, data: Any) -> Any:
        """JSONデータ内の機密情報をマスクする"""
        if isinstance(data, dict):
            masked_data = {}
            sensitive_keys = ["password", "token", "secret", "key", "authorization", "credential"]
            
            for key, value in data.items():
                lowercase_key = key.lower()
                if any(sensitive in lowercase_key for sensitive in sensitive_keys):
                    masked_data[key] = "[MASKED]"
                else:
                    masked_data[key] = self._mask_sensitive_json(value)
            return masked_data
        elif isinstance(data, list):
            return [self._mask_sensitive_json(item) for item in data]
        else:
            return data


async def enhanced_ip_guard(request: Request, call_next):
    """IPアドレス制限とログ記録を行うミドルウェア関数"""
    # リクエスト時間を記録
    start_time = time.time()
    
    try:
        # リクエスト情報（短縮バージョン）
        method = request.method
        path = request.url.path
        client_ip = request.headers.get("X-Forwarded-For", "")
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"
        if client_ip and "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        
        logger.debug(f"IPガード処理: {method} {path} from {client_ip}")
        
        # IPアドレス制限のチェック
        limit_remote_addr(request)
        
        # 実際のリクエスト処理
        response = await call_next(request)
        
        # 処理時間の計算
        process_time = time.time() - start_time
        
        # 処理時間をレスポンスヘッダーに追加（すでに追加されていない場合）
        if "X-Process-Time" not in response.headers:
            response.headers["X-Process-Time"] = str(round(process_time, 6))
        
        # 短縮バージョンのレスポンスログ
        logger.debug(
            f"IPガード許可: {method} {path} from {client_ip} -> {response.status_code} "
            f"(処理時間: {round(process_time * 1000, 2)}ms)"
        )
        
        return response
    except HTTPException as exc:
        # エラー処理時間の計算
        process_time = time.time() - start_time
        
        # エラーログ出力
        logger.error(
            f"IPアクセス制限エラー: status_code={exc.status_code}, detail={exc.detail}, "
            f"process_time={round(process_time * 1000, 2)}ms"
        )
        
        # エラーレスポンスの作成
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})