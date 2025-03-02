#!/bin/bash

# 環境変数がすでに設定されているのでファイルからの読み込みは不要

# 環境変数値を表示
echo "DEBUG mode: $DEBUG"
echo "Using PORT: $PORT"
echo "GCR mode: $GCR"

# GCRが0以外の場合は認証情報フォルダを削除
if [ "$GCR" != "0" ]; then
  echo "Running in Google Cloud Run environment, removing credentials folder..."
  rm -rf /app/backend/credentials
fi


  exec python app.py
fi