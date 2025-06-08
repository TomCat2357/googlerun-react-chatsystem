FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04
# 1. システム依存パッケージのインストール

# 5. 作業ディレクトリ
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip ffmpeg git  && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. pipアップグレード
RUN python3.10 -m pip install --upgrade pip

# 必要なパッケージをインストール
COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r ./requirements.txt

ARG MODE=production

ENV MODE=${MODE}

RUN echo "Using Config_MODE: $MODE"


# アプリケーションファイルのコピー
COPY ./whisper_batch/app/*.py /app
COPY ./whisper_batch/app/config /app/config
COPY ./whisper_batch/app/config_${MODE} ./app/config_${MODE}
COPY ./common_utils /common_utils


# 必要に応じて実行権限を付与（オプション）
RUN chmod +x /app/*.py

# 6. デフォルトコマンド（メインのPythonスクリプトに変更）
# バッチ処理のメインスクリプトを実行
CMD ["python3", "/app/main.py"]
