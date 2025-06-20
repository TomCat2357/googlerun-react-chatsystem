FROM python:3.11-slim

WORKDIR /backend

# 必要なパッケージをインストール
COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r ./requirements.txt



# ビルド時にARGで環境変数を受け取る
ARG PORT=8080
ARG DEBUG=0
ARG MODE=production

#受け取った環境変数をENVに設定
ENV PORT=${PORT}
ENV DEBUG=${DEBUG}
ENV MODE=${MODE}

# 環境変数値を表示
RUN echo "DEBUG mode: $DEBUG"
RUN echo "Using PORT: $PORT"
RUN echo "Using CONFIG_MODE: $MODE"

# バックエンドのコードをコピー
COPY ./app/ ./app/
COPY ./config/ ./config/
COPY ./config_${MODE} ./config_${MODE}

# フロントエンドのビルド済みファイルをコピー
COPY ./frontend/dist/ ./frontend/dist/

# 作業ディレクトリを変更
WORKDIR /backend

# スクリプトを実行

CMD ["python", "-m", "app.main"]
