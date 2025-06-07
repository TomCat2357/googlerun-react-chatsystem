# Google Cloud Run React チャットシステム

## プロジェクト概要
React フロントエンド + FastAPI バックエンド + Whisper バッチ処理による統合チャットシステム。
Google Cloud Platform で稼働し、AI チャット・画像生成・音声文字起こし・位置情報機能を提供。

## 技術スタック
- **フロントエンド**: React + TypeScript + Vite + Tailwind CSS
- **バックエンド**: FastAPI + Hypercorn + Firebase/Firestore
- **バッチ処理**: Whisper + Pyannote.audio + GCP Batch
- **AI/ML**: Vertex AI (Gemini, Imagen), Google Cloud Speech-to-Text
- **インフラ**: Google Cloud Run, Cloud Storage, Pub/Sub

## ディレクトリ構造
```
├── backend/           # FastAPI アプリ
├── frontend/          # React アプリ  
├── whisper_batch/     # 音声バッチ処理
├── common_utils/      # 共通ユーティリティ
└── tests/            # テストコード
```

## 開発コマンド
```bash
# 開発サーバー起動
cd frontend && npm run dev          # フロントエンド
cd backend && python -m app.main   # バックエンド
python tests/app/gcp_emulator_run.py # エミュレータ

# テスト実行
pytest                              # 全体テスト
cd backend && pytest               # バックエンドのみ

# ビルド
cd frontend && npm run build       # フロントエンドビルド
docker build -f backend/backend_frontend.dockerfile . # 本番イメージ
```

## 重要な設定
- **環境変数**: `backend/config/.env.sample`, `frontend/.env.local.sample` を参考に設定
- **認証**: Firebase Authentication + サービスアカウントキー
- **API設定**: Google Cloud の各種API（Vertex AI, Speech-to-Text, Maps）有効化が必要

## コーディングルール
- **Python**: Black フォーマット, 型ヒント必須, `common_utils.logger` 使用
- **TypeScript**: ESLint準拠, 関数コンポーネント + Hooks, Tailwind CSS のみ
- **Git**: 日本語コミットメッセージ, 実際のコミットは禁止（メッセージのみ出力）

## 主な機能
1. **AI チャット**: Gemini モデルによるマルチモーダルチャット
2. **画像生成**: Imagen による AI 画像生成
3. **音声文字起こし**: リアルタイム + Whisper バッチ処理（話者分離付き）
4. **位置情報**: Google Maps API による住所検索・地図表示

## トラブルシューティング
- **認証エラー**: Firebase 設定・サービスアカウント確認
- **CORS エラー**: `ORIGINS` 環境変数確認  
- **音声エラー**: ffmpeg インストール・CUDA 環境確認
- **デバッグ**: `DEBUG=1` 環境変数でログ詳細化