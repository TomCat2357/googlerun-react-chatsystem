#%%
import os
import ipaddress
from flask import Flask, request, abort, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from utils.logger import *
from functools import wraps

app = Flask(__name__)

# .env.gateway から環境変数を読み込み
load_dotenv("./config/.env.gateway")
FRONTEND_PATH = os.environ.get('FRONTEND_PATH')
BACKEND_PATH = os.environ.get('BACKEND_PATH')

# CORS設定
origins = [f"http://localhost:{os.getenv('PORT', 5555)}"]
if int(os.getenv("DEBUG", 0)):
    origins.append("http://localhost:5173")
CORS(
    app,
    origins=origins,
    supports_credentials=False,
    expose_headers=["Authorization"],
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "OPTIONS"],
)

# 環境変数から ALLOWED_IPS を取得（例："127.0.0.1/24,192.168.1.10"）
gateway_env = os.environ.get('ALLOWED_IPS', '')
allowed_tokens = [s.strip() for s in gateway_env.split(',') if s.strip()]

# 許可されたIPアドレス/ネットワークをipaddressオブジェクトに変換
allowed_networks = []
for token in allowed_tokens:
    try:
        # CIDRフォーマット（例：192.168.1.0/24）の場合
        if '/' in token:
            network = ipaddress.ip_network(token, strict=False)
            allowed_networks.append(network)
        # 単一IPアドレスの場合
        else:
            ip = ipaddress.ip_address(token)
            # 単一IPを /32 (IPv4) または /128 (IPv6) のネットワークとして扱う
            network = ipaddress.ip_network(f"{ip}/{'32' if ip.version == 4 else '128'}")
            allowed_networks.append(network)
    except ValueError as e:
        logger.error(f"無効なIPアドレスまたはネットワーク形式: {token}, エラー: {e}")

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
        abort(400, description="不正なIPアドレス形式です")
    
    # 許可されたIPネットワークのリストが空の場合は全て許可
    if not allowed_networks:
        logger.warning("許可されたIPネットワークが設定されていません。全てのIPからのアクセスを許可します。")
        return
    
    # IPがいずれかの許可されたネットワークに含まれているかチェック
    for network in allowed_networks:
        if client_ip in network:
            return  # 許可されている場合、処理継続
    
    # どのネットワークにも含まれていない場合はアクセス拒否
    abort(403, description="アクセスが許可されていません")

# IP制限の処理をデコレーター化
def allowed_ip_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        limit_remote_addr()  # 呼び出し時にIPチェックを実施
        return func(*args, **kwargs)
    return wrapper

@app.route("/")
@allowed_ip_required
def render_frontend():
    logger.info(f"Frontend request received {os.path.join(FRONTEND_PATH, 'index.html')}")
    return send_from_directory(FRONTEND_PATH, "index.html")


@app.route("/backend/<path:path>")
@allowed_ip_required
def serve_backend_static(path):
    logger.info(f"Backend request received: {path}")
    return send_from_directory(os.path.join(BACKEND_PATH, 'backend'), path)
#%%
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=os.getenv("PORT", 5555), debug=int(os.getenv("DEBUG", 0)))