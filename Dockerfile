FROM python:3.11-slim

WORKDIR /app

# 必要なパッケージをインストール
COPY backend/config/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt uvicorn

# バックエンドのコードをコピー
COPY backend/ ./backend/

# フロントエンドのビルド済みファイルをコピー
COPY frontend/dist/ ./frontend/dist/

# 環境変数の設定
ENV FRONTEND_PATH=/app/frontend/dist
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/backend/config/firebase_credential.json

# 作業ディレクトリを変更
WORKDIR /app/backend

# シェルスクリプトを追加して起動方法を条件分岐
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# スクリプトを実行
CMD ["/app/start.sh"]