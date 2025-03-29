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
COPY config/requirements.txt config/requirements.txt
RUN pip install --no-cache-dir -r config/requirements.txt

ARG MODE=production

ENV MODE=${MODE}

RUN echo "Using Config_MODE: $MODE"


# アプリケーションファイルのコピー
COPY ./app/*.py /app
COPY ./app/config /app/config
COPY ./app/config_${MODE} ./backend/config_${MODE}


# 必要に応じて実行権限を付与（オプション）
RUN chmod +x /app/*.py

# 6. デフォルトコマンド（メインのPythonスクリプトに変更）
# 例: main.pyというファイルがある場合
#CMD ["python3", "/app/main.py"]
CMD ["bash"]
