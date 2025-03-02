FROM python:3.11-slim

WORKDIR /app

# 必要なパッケージをインストール
COPY backend/config/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# バックエンドのコードをコピー
COPY backend/ ./backend/

# フロントエンドのビルド済みファイルをコピー
COPY frontend/dist/ ./frontend/dist/

# 環境変数の設定
ENV FRONTEND_PATH=/app/frontend/dist
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/backend/config/firebase_credential.json

# 作業ディレクトリを変更
WORKDIR /app/backend

# ポート8080を公開
EXPOSE 8080

# アプリケーションを実行
CMD ["python", "app.py"]