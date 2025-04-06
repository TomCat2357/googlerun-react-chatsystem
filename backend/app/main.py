# main.py - FastAPIアプリケーションのエントリーポイント

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from common_utils.logger import logger
from fastapi import Request

# API ルーターのインポート
from app.api.geocoding import router as geocoding_router
from app.api.chat import router as chat_router
from app.api.config import router as config_router
from app.api.auth import router as auth_router
from app.api.speech import router as speech_router
from app.api.image import router as image_router
from app.api.whisper import router as whisper_router

# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# ===== アプリケーション設定 =====
PORT = int(os.environ.get("PORT", "8080"))
FRONTEND_PATH = os.environ["FRONTEND_PATH"]

# CORS設定
ORIGINS = [org for org in os.environ.get("ORIGINS", "").split(",") if org]

# IPアクセス制限
ALLOWED_IPS = os.environ.get("ALLOWED_IPS")

# ===== Firebase設定 =====
FIREBASE_CLIENT_SECRET_PATH = os.environ.get("FIREBASE_CLIENT_SECRET_PATH", "")

# ===== リクエストIDが不要なパス設定 =====
UNNEED_REQUEST_ID_PATH = os.environ.get("UNNEED_REQUEST_ID_PATH", "").split(",")
UNNEED_REQUEST_ID_PATH_STARTSWITH = os.environ.get("UNNEED_REQUEST_ID_PATH_STARTSWITH", "").split(",")
UNNEED_REQUEST_ID_PATH_ENDSWITH = os.environ.get("UNNEED_REQUEST_ID_PATH_ENDSWITH", "").split(",")

# ログでマスクするセンシティブ情報
SENSITIVE_KEYS = os.environ["SENSITIVE_KEYS"].split(",")

# Firebase Admin SDKの初期化
try:
    # 初期化されているかチェック
    firebase_admin.get_app()
    logger.debug("Firebase既に初期化済み")
except ValueError:
    # 初期化されていない場合のみ初期化
    if os.path.exists(FIREBASE_CLIENT_SECRET_PATH):
        logger.debug(f"Firebase認証情報を読み込み: {FIREBASE_CLIENT_SECRET_PATH}")
        cred = credentials.Certificate(FIREBASE_CLIENT_SECRET_PATH)
        firebase_admin.initialize_app(cred)  # 名前を指定しない
    else:
        logger.debug("Firebase認証情報なしで初期化")
        firebase_admin.initialize_app()  # 名前を指定しない

# FastAPIアプリケーションの初期化
app = FastAPI()

logger.debug("ORIGINS: %s", ORIGINS)

# FastAPIのCORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-Id"],
    expose_headers=["Authorization"],
)

# ミドルウェアのインポート
from app.api.auth import log_request_middleware

# ミドルウェアの登録
app.add_middleware(log_request_middleware)

# ルーターの登録
app.include_router(geocoding_router, prefix="/backend")
app.include_router(chat_router, prefix="/backend")
app.include_router(config_router, prefix="/backend")
app.include_router(auth_router, prefix="/backend")
app.include_router(speech_router, prefix="/backend")
app.include_router(image_router, prefix="/backend")
app.include_router(whisper_router, prefix="/backend")

# 静的ファイル配信設定
app.mount(
    "/assets",
    StaticFiles(directory=os.path.join(FRONTEND_PATH, "assets")),
    name="assets",
)

@app.get("/vite.svg")
async def vite_svg():
    from fastapi.responses import FileResponse
    logger.debug("vite.svg リクエスト")
    svg_path = os.path.join(FRONTEND_PATH, "vite.svg")
    if os.path.isfile(svg_path):
        return FileResponse(svg_path, media_type="image/svg+xml")

    logger.warning(f"vite.svg が見つかりません。確認パス: {svg_path}")
    try:
        logger.debug(f"FRONTEND_PATH: {FRONTEND_PATH}")
        logger.debug(f"FRONTEND_PATH内のファイル一覧: {os.listdir(FRONTEND_PATH)}")
    except Exception as e:
        logger.error(f"FRONTEND_PATH内のファイル一覧取得エラー: {e}")

    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="ファイルが見つかりません")

@app.get("/")
async def index():
    from fastapi.responses import FileResponse
    logger.debug("インデックスページリクエスト: %s", FRONTEND_PATH)
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))

@app.get("/{path:path}")
async def static_file(path: str):
    from fastapi.responses import FileResponse
    logger.debug(f"パスリクエスト: /{path}")
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))

# アプリケーション起動部分
if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    # Hypercornの設定
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    config.loglevel = "info"
    config.workers = 1

    # SSL/TLS設定（証明書と秘密鍵のパスを指定）
    SSL_CERT_PATH = os.environ.get("SSL_CERT_PATH", "")
    SSL_KEY_PATH = os.environ.get("SSL_KEY_PATH", "")
    
    if (
        SSL_CERT_PATH
        and SSL_KEY_PATH
        and os.path.exists(SSL_CERT_PATH)
        and os.path.exists(SSL_KEY_PATH)
    ):
        config.certfile = SSL_CERT_PATH
        config.keyfile = SSL_KEY_PATH
        # SSLプロトコルを明示的に設定して安全性と互換性を確保
        config.ciphers = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20"
        logger.info("SSL/TLSが有効化されました")

        # HTTP/2を有効化し優先する
        config.alpn_protocols = ["h2", "http/1.1"]
        config.h2_max_concurrent_streams = 250  # HTTP/2の同時ストリーム数を設定
        config.h2_max_inbound_frame_size = 2**14  # HTTP/2フレームの最大サイズを設定
        logger.info("HTTP/2が有効化されました")
    else:
        logger.warning(
            "SSL/TLS証明書が見つからないか設定されていません。HTTP/1.1のみで動作します"
        )
        # HTTP/1.1のみを使用
        config.alpn_protocols = ["http/1.1"]

    logger.info(
        "Hypercornを使用してFastAPIアプリを起動します（TLS設定：%s）",
        "有効" if hasattr(config, "certfile") else "無効",
    )

    # Hypercornでアプリを起動
    import asyncio
    asyncio.run(hypercorn.asyncio.serve(app, config))