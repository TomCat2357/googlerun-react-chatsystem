FROM python:3.11-slim

WORKDIR /app

# ビルド時にARGで環境変数を受け取る
ARG PORT=8000
ARG DEBUG=0
ARG MODE=production

#受け取った環境変数をENVに設定
ENV PORT=${PORT}
ENV DEBUG=${DEBUG}
ENV MODE=${MODE}

# 環境変数値を表示
RUN echo "DEBUG mode: $DEBUG"
RUN echo "Using PORT: $PORT"
RUN echo "Using CONFIG_PATH: $MODE"

# バックエンドのコードをコピー
COPY ./backend/config/ ./backend/config/
COPY ./backend/utils/ ./backend/utils/
COPY ./backend/app.py ./backend/app.py
COPY ./backend/config_${MODE} ./backend/config_${MODE}

# 必要なパッケージをインストール
RUN pip install --no-cache-dir -r ./backend/config/requirements.txt

# フロントエンドのビルド済みファイルをコピー
COPY ./frontend/dist/ ./frontend/dist/

# 作業ディレクトリを変更
WORKDIR /app/backend

# スクリプトを実行

CMD ["python", "app.py"]
