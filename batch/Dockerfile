FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04
# 1. システム依存パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip ffmpeg git  && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. pipアップグレード
RUN python3.10 -m pip install --upgrade pip

# 4. pyannote.audio, faster-whisper, CTranslate2のインストール
RUN python3.10 -m pip install pyannote.audio faster-whisper polars google-cloud-storage

# 5. 作業ディレクトリ
WORKDIR /app

# アプリケーションファイルのコピー
COPY ./app /app

# 必要に応じて実行権限を付与（オプション）
RUN chmod +x /app/*.py

# 6. デフォルトコマンド（メインのPythonスクリプトに変更）
# 例: main.pyというファイルがある場合
CMD ["python3", "/app/main.py"]
