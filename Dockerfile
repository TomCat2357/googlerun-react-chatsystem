FROM python:3.11-slim

WORKDIR /app

# 必要なファイルをコピー
COPY ./app.py .
COPY ./backend/config/ ./backend/config/
COPY ./frontend/dist/ ./frontend/dist/

# 依存関係のインストール
RUN pip install --no-cache-dir -r ./config/requirements.txt

# サーバー起動
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "0", "app:app"]
