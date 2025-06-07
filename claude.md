# Google Cloud Run React チャットシステム - プロジェクト設定

## プロジェクト概要

React フロントエンド、FastAPI バックエンド、Whisper 音声文字起こしバッチ処理を統合したチャットシステムです。Google Cloud Platform (GCP) で本番稼働し、オンプレミスからインターネット接続で利用できます。

## 技術スタック

### フロントエンド
- **React** (TypeScript, Vite)
- **Tailwind CSS** (スタイリング)
- **Firebase Authentication** (認証)
- **IndexedDB** (キャッシュ)

### バックエンド
- **FastAPI + Hypercorn** (APIサーバー)
- **Firebase/Firestore** (認証・データベース)
- **Google Cloud Storage** (ファイル保存)
- **Vertex AI** (Gemini チャット、Imagen 画像生成)
- **Google Cloud Speech-to-Text** (音声認識)
- **Google Maps API** (位置情報)

### バッチ処理
- **Whisper** (音声文字起こし)
- **Pyannote.audio** (話者分け)
- **GCP Batch** (バッチ実行環境)
- **Pub/Sub** (非同期メッセージング)

## ディレクトリ構造

```
/mnt/c/Users/gk3t-/OneDrive - 又村 友幸/working/googlerun-react-chatsystem/
├── backend/                    # FastAPI バックエンド
│   ├── app/                   # アプリケーションコード
│   │   ├── api/              # エンドポイント定義
│   │   ├── services/         # ビジネスロジック
│   │   ├── utils/            # ユーティリティ
│   │   └── main.py           # アプリエントリーポイント
│   ├── config/               # 環境設定ファイル
│   └── requirements.txt      # Python依存関係
├── frontend/                  # React フロントエンド
│   ├── src/                  # ソースコード
│   │   ├── components/       # React コンポーネント
│   │   ├── contexts/         # React コンテキスト
│   │   ├── firebase/         # Firebase設定
│   │   └── utils/            # ユーティリティ
│   ├── package.json          # Node.js依存関係
│   └── .env.local.sample     # 環境変数サンプル
├── whisper_batch/            # バッチ処理
│   ├── app/                  # バッチアプリケーション
│   └── config/               # バッチ用設定
├── common_utils/             # 共通ユーティリティ
└── tests/                    # テストコード
```

## 重要な設定ファイル

- `backend/config/.env.sample` - バックエンド環境変数のサンプル
- `frontend/.env.local.sample` - フロントエンド環境変数のサンプル
- `backend/backend_frontend.dockerfile` - 本番デプロイ用Dockerfile
- `whisper_batch/whisper_batch.dockerfile` - バッチ処理用Dockerfile

## 開発ワークフロー

### セットアップ手順
1. 環境変数ファイルを `.sample` から実際の設定にコピー・編集
2. Firebase プロジェクトとサービスアカウント設定
3. Google Cloud プロジェクト設定とAPI有効化
4. 依存関係インストール (`pip install -r requirements.txt`, `npm install`)

### ローカル開発
- **フロントエンド**: `cd frontend && npm run dev` (Vite開発サーバー)
- **バックエンド**: `cd backend && python -m app.main` (FastAPI開発サーバー)
- **エミュレータ**: `python tests/app/gcp_emulator_run.py` (Firestore/GCS エミュレータ)

### 本番デプロイ
- **Cloud Run**: `backend/backend_frontend.dockerfile` を使用
- **GCP Batch**: `whisper_batch/whisper_batch.dockerfile` を使用

## コーディング規則

### Python (Backend/Batch)
- **スタイル**: Black フォーマッター、型ヒント必須
- **依存性注入**: FastAPI の Dependency Injection 活用
- **エラーハンドリング**: try-except で適切な例外処理
- **ログ**: `common_utils/logger.py` の統一ログシステム使用
- **設定**: 環境変数による設定管理（`.env` ファイル）

### TypeScript/React (Frontend)
- **スタイル**: ESLint 設定に従う
- **コンポーネント**: 関数コンポーネント + Hooks パターン
- **状態管理**: React Context API、必要に応じて useState/useReducer
- **スタイリング**: Tailwind CSS クラス使用
- **ファイル構成**: feature-based ディレクトリ構造

### Git 運用
- **ブランチ**: feature/機能名 でブランチ作成
- **コミット**: 日本語での説明的コミットメッセージ
- **禁止事項**: 実際のコミットは行わない（コミットメッセージのみ出力）

## セキュリティ考慮事項

- Firebase Authentication による認証
- CORS 設定によるアクセス制限
- IPアドレス制限（本番環境）
- ファイルサイズ・形式の制限
- Google Cloud IAM による権限管理

## テスト戦略

- **Unit Tests**: pytest による単体テスト
- **Integration Tests**: GCP エミュレータを使った統合テスト
- **E2E Tests**: 主要な画面フローのテスト
- **テスト設定**: 各モジュールに `pytest.ini` 配置

## パフォーマンス最適化

- **キャッシュ**: IndexedDB（フロント）、メモリキャッシュ（バック）
- **ファイル処理**: 画像リサイズ、音声形式変換
- **バッチ処理**: 非同期処理によるスケーラビリティ
- **CDN**: 静的ファイルの配信最適化

## 監視・ログ

- **ログレベル**: DEBUG 環境変数による制御
- **データサニタイズ**: 機密情報のマスキング
- **リクエストログ**: API呼び出しの追跡
- **エラー監視**: 例外の集中管理

## よく使用するコマンド

### 開発環境起動
```bash
# フロントエンド開発サーバー
cd frontend && npm run dev

# バックエンド開発サーバー
cd backend && python -m app.main

# GCP エミュレータ起動
python tests/app/gcp_emulator_run.py
```

### ビルド・デプロイ
```bash
# フロントエンドビルド
cd frontend && npm run build

# Docker イメージビルド（バックエンド）
docker build -f backend_frontend.dockerfile -t chat-system .

# Docker イメージビルド（バッチ）
docker build -f whisper_batch.dockerfile -t whisper-batch .
```

### テスト実行
```bash
# バックエンドテスト
cd backend && pytest

# バッチ処理テスト
cd whisper_batch && pytest

# 全体テスト
pytest
```

## トラブルシューティング

### よくある問題
1. **認証エラー**: Firebase設定・サービスアカウントキーの確認
2. **CORS エラー**: `ORIGINS` 環境変数の設定確認
3. **ファイルアップロード失敗**: サイズ制限・形式チェック
4. **音声処理エラー**: ffmpeg インストール、CUDA 環境確認

### デバッグ方法
- `DEBUG=1` 環境変数でデバッグログ有効化
- ブラウザ開発者ツールでネットワーク・コンソール確認
- GCP ログエクスプローラーでクラウドログ確認

## 外部サービス連携

### Google Cloud Services
- **Vertex AI**: チャット（Gemini）、画像生成（Imagen）
- **Speech-to-Text**: リアルタイム音声認識
- **Cloud Storage**: ファイル保存・配信
- **Firestore**: メタデータ・ジョブキュー管理
- **Cloud Run**: アプリケーションホスティング
- **Batch**: バッチ処理実行

### Firebase Services
- **Authentication**: ユーザー認証
- **Firestore**: リアルタイムデータベース

### Third-party APIs
- **Google Maps API**: 住所検索・地図表示
- **HuggingFace**: Pyannote モデルアクセス

## 開発時の注意事項

- 環境変数ファイル（`.env`）はコミットしない
- サービスアカウントキーファイルはコミットしない
- 大きなファイル（音声・画像）はGit LFSまたはクラウドストレージ使用
- テスト用データは `tests/` ディレクトリに配置
- ドキュメント更新はコード変更と同時に実施

プロジェクト固有の要件や技術的制約を理解し、一貫性のあるコード品質を維持することを優先してください。