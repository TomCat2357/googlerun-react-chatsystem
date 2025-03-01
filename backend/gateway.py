import ipaddress, ipaddress, os, time, requests
from flask import Flask, request, abort, send_from_directory, Response
from dotenv import load_dotenv
from utils.logger import *
from functools import wraps

app = Flask(__name__)

# .env.gateway から環境変数を読み込み
load_dotenv("./config/.env.gateway")
FRONTEND_PATH = os.environ.get('FRONTEND_PATH')
BACKEND_PATH = os.environ.get('BACKEND_PATH')

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
    """リクエスト送信元IPが許可リストに含まれていなければ403を返す
    abortのときの0.05休みはDDos防止のため
    """
    remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr)
    logger.info(f"X-Forwarded-For: {remote_addr}")
    if remote_addr and ',' in remote_addr:
        remote_addr = remote_addr.split(',')[0].strip()
    try:
        client_ip = ipaddress.ip_address(remote_addr)
        logger.info(f"リクエスト送信元IP: {client_ip}")
    except ValueError:
        time.sleep(0.05)
        abort(400, description="不正なIPアドレス形式です")
    
    # IPがいずれかの許可されたネットワークに含まれているかチェック
    for network in allowed_networks:
        if client_ip in network:
            return  # 許可されている場合、処理継続
    
    # どのネットワークにも含まれていない場合はアクセス拒否
    time.sleep(0.05)
    abort(403, description="アクセスが許可されていません")

# IP制限の処理をデコレーター化
def allowed_ip_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        limit_remote_addr()  # 呼び出し時にIPチェックを実施
        return func(*args, **kwargs)
    return wrapper

# バックエンドへのプロキシルート
@app.route('/backend/<path:path>', methods=['GET', 'POST', 'OPTIONS'])
@allowed_ip_required
def proxy_backend(path):
    logger.info(f"バックエンドへのプロキシリクエスト: {path}")
    
    # リクエストURLの構築
    target_url = f"{BACKEND_PATH}/backend/{path}"
    logger.info(f"転送先URL: {target_url}")
    
    # オリジナルのリクエストヘッダーをコピー
    headers = {key: value for key, value in request.headers.items()
               if key.lower() not in ['host', 'content-length']}
    
    # リクエストメソッドに基づいて適切なリクエストを送信
    try:
        if request.method == 'GET':
            resp = requests.get(
                target_url,
                params=request.args,
                headers=headers,
                cookies=request.cookies,
                stream=True
            )
        elif request.method == 'POST':
            resp = requests.post(
                target_url,
                json=request.get_json() if request.is_json else None,
                data=request.form if not request.is_json else None,
                files=request.files if request.files else None,
                headers=headers,
                cookies=request.cookies,
                stream=True
            )
        elif request.method == 'OPTIONS':
            resp = requests.options(
                target_url,
                headers=headers,
                cookies=request.cookies
            )
        else:
            return Response("メソッド未対応", status=405)
        
        # バックエンドからのレスポンスヘッダーを抽出
        response_headers = [(key, value) for key, value in resp.headers.items()
                           if key.lower() not in ['content-length', 'connection', 'transfer-encoding']]
        
        # ストリーミングレスポンスを返す
        return Response(
            resp.iter_content(chunk_size=10*1024),
            status=resp.status_code,
            headers=response_headers,
            content_type=resp.headers.get('Content-Type', 'text/plain')
        )
        
    except requests.RequestException as e:
        logger.error(f"バックエンドプロキシエラー: {str(e)}")
        return Response(f"バックエンド接続エラー: {str(e)}", status=500)

    
# アセットファイルを処理（assets/ディレクトリ内のファイル用）
@app.route("/assets/<path:path>")
@allowed_ip_required
def serve_assets(path):
    logger.info(f"アセットファイルリクエスト: /assets/{path}")
    assets_dir = os.path.join(FRONTEND_PATH, "assets")
    if os.path.exists(assets_dir) and os.path.isfile(os.path.join(assets_dir, path)):
        return send_from_directory(assets_dir, path)
    else:
        logger.warning(f"アセットファイルが見つかりません: {path}")
        if not os.path.exists(assets_dir):
            logger.error(f"アセットディレクトリが存在しません: {assets_dir}")
        abort(404)



# Viteファビコンルート
@app.route("/vite.svg")
@allowed_ip_required
def vite_svg():
    logger.info("vite.svg リクエスト")
    svg_path = os.path.join(FRONTEND_PATH, "vite.svg")
    if os.path.isfile(svg_path):
        # 明示的にMIMEタイプを指定
        return send_from_directory(FRONTEND_PATH, "vite.svg", mimetype="image/svg+xml")
    
    logger.warning(f"vite.svg が見つかりません。確認パス: {svg_path}")
    # ファイルが見つからない場合はFRONTEND_PATHの内容をログに出力
    try:
        logger.info(f"FRONTEND_PATH: {FRONTEND_PATH}")
        logger.info(f"FRONTEND_PATH内のファイル一覧: {os.listdir(FRONTEND_PATH)}")
    except Exception as e:
        logger.error(f"FRONTEND_PATH内のファイル一覧取得エラー: {e}")
    
    abort(404)




# ルートパス
@app.route("/<path:path>", methods=["GET"])
@allowed_ip_required
def index(path=""):
    logger.info("インデックスページリクエスト: %s", path)
    return send_from_directory(FRONTEND_PATH, "index.html")
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=os.getenv("PORT", 5555), debug=int(os.getenv("DEBUG", 0)))