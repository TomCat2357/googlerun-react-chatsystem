FROM python:3.11-slim

WORKDIR /app

# 必要なパッケージをインストール
COPY backend/config/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ビルド時にARGで環境変数を受け取る
ARG PORT
ARG DEBUG
ARG CREDENTIALS_PATH

# 受け取った環境変数をENVに設定
ENV PORT=${PORT:-8000}
ENV DEBUG=${DEBUG:-1}
ENV CREDENTIALS_PATH=${CREDENTIALS_PATH:-void}

# 環境変数値を表示
RUN echo "DEBUG mode: $DEBUG"
RUN echo "Using PORT: $PORT"
RUN echo "Using CREDENTIALS_PATH: $CREDENTIALS_PATH"

# バックエンドのコードをコピー
COPY backend/config/ ./backend/config/
COPY backend/utils/ ./backend/utils/
COPY backend/app.py ./backend/app.py
COPY backend/${CREDENTIALS_PATH} ./backend/${CREDENTIALS_PATH}

# フロントエンドのビルド済みファイルをコピー
COPY frontend/dist/ ./frontend/dist/

# 作業ディレクトリを変更
WORKDIR /app/backend




# スクリプトを実行

CMD ["python", "app.py"]
