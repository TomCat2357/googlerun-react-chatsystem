FROM python:3.11-slim

WORKDIR /app

# 必要なパッケージをインストール
COPY backend/config/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# バックエンドのコードをコピー
COPY backend/ ./backend/

# フロントエンドのビルド済みファイルをコピー
COPY frontend/dist/ ./frontend/dist/

# 作業ディレクトリを変更
WORKDIR /app/backend

# シェルスクリプトを追加して起動方法を条件分岐
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# ビルド時にARGで環境変数を受け取る
ARG PORT
ARG DEBUG

# 受け取った環境変数をENVに設定
ENV PORT=${PORT:-8000}
ENV DEBUG=${DEBUG:-1}

# 環境変数値を表示
RUN echo "DEBUG mode: $DEBUG"
RUN echo "Using PORT: $PORT"

# スクリプトを実行

CMD ["python", "app.py"]
