#!/bin/bash

# 環境変数DEBUGがdocker-compose経由で設定されているか確認
# 設定されていない場合は.envファイルから読み込む
if [ -z "$DEBUG" ]; then
  # .envファイルからDEBUGを読み込む
  if [ -f /app/backend/config/.env ]; then
    source /app/backend/config/.env
  fi
fi

# PORTが設定されていない場合は.envから読み込み、それでもなければデフォルト値
if [ -z "$PORT" ]; then
  if [ -f /app/backend/config/.env ]; then
    source /app/backend/config/.env
  fi
  # それでもPORTが設定されていない場合はデフォルト値を使用
  if [ -z "$PORT" ]; then
    PORT=8080
  fi
fi

echo "DEBUG mode: $DEBUG"
echo "Using PORT: $PORT"

# DEBUG=0の場合はUvicornで起動
if [ "$DEBUG" = "0" ]; then
  echo "Starting with Uvicorn in production mode..."
  exec uvicorn app:app --host 0.0.0.0 --port $PORT
else
  echo "Starting with Flask development server..."
  exec python app.py
fi