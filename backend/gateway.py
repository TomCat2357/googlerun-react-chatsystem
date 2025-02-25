#%%
import os
import ipaddress
from flask import Flask, request, abort, send_from_directory
from dotenv import load_dotenv
from utils.logger import *
from functools import wraps

FRONTEND_PATH = os.environ.get('FRONTEND_PATH')

# .env.gateway から環境変数を読み込み
load_dotenv("./config/.env.gateway")

app = Flask(__name__)

# 環境変数から ALLOWED_IPS を取得（例："127.0.0.1/24,192.168.1.10"）
gateway_env = os.environ.get('ALLOWED_IPS', '')
allowed_tokens = [s.strip() for s in gateway_env.split(',') if s.strip()]

allowed_networks = []

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
    for network in allowed_networks:
        if client_ip in network:
            return  # 許可されている場合、処理継続
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
def index():
    return send_from_directory(FRONTEND_PATH, "index.html")

@app.route("/<path:path>")
@allowed_ip_required
def static_file(path):
    return send_from_directory(FRONTEND_PATH, path)



#%%
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5555)

# %%
