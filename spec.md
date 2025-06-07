# Google Cloud Run React チャットシステム 仕様書

## 1. システム概要

### 1.1 目的
AI チャット、画像生成、音声文字起こし、位置情報サービスを統合したWebアプリケーション

### 1.2 アーキテクチャ
- **フロントエンド**: React SPA（Single Page Application）
- **バックエンド**: FastAPI REST API
- **バッチ処理**: Whisper + Pyannote による音声処理
- **インフラ**: Google Cloud Platform
- **認証**: Firebase Authentication
- **データベース**: Firestore
- **ストレージ**: Cloud Storage

### 1.3 デプロイ環境
- **本番**: Google Cloud Run
- **アクセス**: オンプレミスからインターネット経由

## 2. 機能仕様

### 2.1 認証機能
- **Firebase Authentication** によるユーザー認証
- ログイン・ログアウト機能
- 認証状態の永続化
- 保護されたルート

### 2.2 チャット機能
- **AI チャット**: Vertex AI Gemini モデル
- **マルチモーダル**: テキスト、画像、音声の添付
- **リアルタイム**: WebSocket による双方向通信
- **履歴管理**: チャット履歴の保存・参照
- **モデル選択**: 複数のGeminiモデルから選択可能

### 2.3 画像生成機能
- **Vertex AI Imagen** による画像生成
- **パラメータ制御**: アスペクト比、品質、セーフティフィルター
- **バッチ生成**: 複数画像の同時生成
- **履歴管理**: 生成履歴の保存

### 2.4 音声文字起こし機能

#### 2.4.1 リアルタイム文字起こし
- **Google Cloud Speech-to-Text** API
- **ライブ音声**: マイクからのリアルタイム認識
- **ファイルアップロード**: 音声ファイルのアップロード処理

#### 2.4.2 バッチ文字起こし（Whisper）
- **高精度文字起こし**: OpenAI Whisper モデル
- **話者分離**: Pyannote.audio による話者識別
- **バッチ処理**: GCP Batch での非同期処理
- **ジョブ管理**: キューイング、ステータス管理、結果取得

### 2.5 位置情報機能
- **住所検索**: Google Maps API による住所→座標変換
- **逆ジオコーディング**: 座標→住所変換
- **地図表示**: 衛星画像、ストリートビュー対応
- **キャッシュ**: IndexedDB による結果キャッシュ

## 3. 技術仕様

### 3.1 フロントエンド技術

#### 3.1.1 コア技術
- **React 18**: 関数コンポーネント + Hooks
- **TypeScript**: 厳格な型チェック
- **Vite**: 高速ビルドツール
- **React Router**: SPA ルーティング

#### 3.1.2 UI・スタイリング
- **Tailwind CSS**: ユーティリティファーストCSS
- **Lucide React**: アイコンライブラリ
- **レスポンシブデザイン**: モバイル対応

#### 3.1.3 状態管理
- **React Context API**: グローバル状態管理
- **useState/useReducer**: ローカル状態管理
- **IndexedDB**: クライアントサイドキャッシュ

#### 3.1.4 ファイル処理
- **PDF.js**: PDFファイル処理
- **Mammoth**: Word文書処理
- **XLSX**: Excel文書処理
- **Canvas API**: 画像リサイズ・圧縮

### 3.2 バックエンド技術

#### 3.2.1 API フレームワーク
- **FastAPI**: 高性能Python Webフレームワーク
- **Pydantic**: データバリデーション
- **Hypercorn**: ASGI サーバー
- **WebSocket**: リアルタイム通信

#### 3.2.2 Google Cloud Services
- **Vertex AI**: Gemini（チャット）、Imagen（画像生成）
- **Cloud Speech-to-Text**: 音声認識
- **Cloud Storage**: ファイル保存
- **Cloud Batch**: バッチ処理実行
- **Pub/Sub**: 非同期メッセージング

#### 3.2.3 データベース・認証
- **Firebase Admin SDK**: サーバーサイド認証
- **Firestore**: NoSQLデータベース
- **Firebase Authentication**: ユーザー認証

### 3.3 バッチ処理技術

#### 3.3.1 音声処理
- **Faster-Whisper**: 高速文字起こし
- **Pyannote.audio**: 話者分離・音声活動検出
- **FFmpeg**: 音声形式変換

#### 3.3.2 実行環境
- **Docker**: コンテナ化
- **NVIDIA CUDA**: GPU アクセラレーション
- **GCP Batch**: スケーラブルバッチ処理

## 4. API 仕様

### 4.1 認証 API
```
POST /api/auth/verify-token
- Firebase IDトークンの検証
- ユーザー情報の取得

POST /api/auth/logout
- セッションの無効化
```

### 4.2 チャット API
```
GET /api/chat/models
- 利用可能なAIモデル一覧

POST /api/chat/stream
- ストリーミングチャット
- WebSocket接続

POST /api/chat/upload
- ファイルアップロード（画像、音声、テキスト）
```

### 4.3 画像生成 API
```
POST /api/generate-image
- テキストプロンプトから画像生成
- パラメータ: アスペクト比、品質、セーフティレベル
```

### 4.4 音声文字起こし API
```
POST /api/speech-to-text
- リアルタイム音声文字起こし

POST /api/whisper/upload
- バッチ文字起こし用音声アップロード

GET /api/whisper/jobs
- ジョブ一覧・ステータス確認

GET /api/whisper/result/{job_id}
- 文字起こし結果取得
```

### 4.5 位置情報 API
```
POST /api/geocoding/address-to-coords
- 住所から座標への変換

POST /api/geocoding/coords-to-address
- 座標から住所への変換

GET /api/geocoding/static-map
- 静的地図画像の取得
```

## 5. データモデル

### 5.1 ユーザー
```typescript
interface User {
  uid: string;
  email: string;
  displayName?: string;
  photoURL?: string;
  lastLoginAt: Date;
}
```

### 5.2 チャットメッセージ
```typescript
interface ChatMessage {
  id: string;
  userId: string;
  content: string;
  role: 'user' | 'assistant';
  attachments?: Attachment[];
  timestamp: Date;
  model?: string;
}

interface Attachment {
  type: 'image' | 'audio' | 'text';
  url: string;
  filename: string;
  size: number;
}
```

### 5.3 Whisper ジョブ
```typescript
interface WhisperJob {
  id: string;
  userId: string;
  audioUrl: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  resultUrl?: string;
  createdAt: Date;
  completedAt?: Date;
  errorMessage?: string;
}
```

### 5.4 画像生成履歴
```typescript
interface ImageGeneration {
  id: string;
  userId: string;
  prompt: string;
  model: string;
  parameters: ImageParameters;
  imageUrls: string[];
  createdAt: Date;
}
```

## 6. セキュリティ仕様

### 6.1 認証・認可
- **Firebase Authentication**: トークンベース認証
- **JWT トークン**: APIアクセス制御
- **ミドルウェア**: 全保護エンドポイントで認証チェック

### 6.2 CORS・アクセス制御
- **CORS**: 許可されたオリジンのみアクセス可能
- **IP制限**: 本番環境でのIPアドレス制限
- **レート制限**: API呼び出し頻度制限

### 6.3 データ保護
- **ファイルサイズ制限**: アップロードファイルサイズ制限
- **ファイル形式検証**: 許可された形式のみ受け入れ
- **ログマスキング**: 機密情報の自動マスキング

### 6.4 Google Cloud セキュリティ
- **IAM**: 最小権限の原則
- **サービスアカウント**: 専用アカウントでの API アクセス
- **VPC**: ネットワークレベルの分離

## 7. パフォーマンス要件

### 7.1 応答時間
- **チャット応答**: 2秒以内（初回レスポンス）
- **画像生成**: 30秒以内
- **リアルタイム文字起こし**: 500ms以内
- **API応答**: 1秒以内（一般的なエンドポイント）

### 7.2 スループット
- **同時ユーザー**: 100ユーザー
- **ファイルアップロード**: 最大256MB
- **バッチ処理**: 1時間あたり100ジョブ

### 7.3 可用性
- **稼働率**: 99.9%以上
- **自動復旧**: 障害からの自動復旧
- **監視**: 24/7 システム監視

## 8. 運用仕様

### 8.1 監視・ログ
- **アプリケーションログ**: 構造化ログによる統一フォーマット
- **アクセスログ**: リクエスト/レスポンスの記録
- **エラー監視**: 例外の自動検知・通知
- **パフォーマンス監視**: レスポンス時間、リソース使用率

### 8.2 バックアップ・復旧
- **データベース**: Firestore の自動バックアップ
- **ファイル**: Cloud Storage の冗長化
- **設定**: 環境設定のバージョン管理

### 8.3 スケーリング
- **水平スケーリング**: Cloud Run の自動スケーリング
- **負荷分散**: Cloud Load Balancer
- **キャッシュ**: 適切なキャッシュ戦略

## 9. 開発・デプロイメント

### 9.1 開発環境
- **ローカル開発**: Docker Compose による統合環境
- **エミュレータ**: Firestore、GCS エミュレータ
- **ホットリロード**: Vite、FastAPI の開発サーバー

### 9.2 CI/CD
- **テスト自動化**: pytest、Jest による自動テスト
- **ビルド自動化**: Docker イメージの自動ビルド
- **デプロイ自動化**: Cloud Run への自動デプロイ

### 9.3 環境管理
- **環境分離**: 開発、ステージング、本番環境
- **設定管理**: 環境変数による設定
- **シークレット管理**: Google Secret Manager

## 10. 制限事項・制約

### 10.1 技術的制約
- **ファイルサイズ**: 最大256MB
- **音声時間**: 最大3時間
- **同時接続**: WebSocket 最大1000接続
- **API制限**: GCP サービスの制限に準拠

### 10.2 ビジネス制約
- **利用料金**: GCP 従量課金
- **データ保持**: ユーザーデータの保持期間
- **地域制限**: 日本国内からのアクセス想定

### 10.3 法的制約
- **データ保護**: 個人情報保護法への準拠
- **AI利用**: 生成AI の適切な利用
- **著作権**: 生成コンテンツの著作権考慮

## 11. 今後の拡張計画

### 11.1 機能拡張
- **多言語対応**: 国際化・ローカライゼーション
- **モバイルアプリ**: React Native による モバイル版
- **オフライン機能**: Progressive Web App 対応
- **協業機能**: 複数ユーザーでの共同作業

### 11.2 技術拡張
- **Edge Computing**: Cloud Functions による エッジ処理
- **MLOps**: カスタムモデルの学習・デプロイ
- **マイクロサービス**: サービス分割による可用性向上

この仕様書は、プロジェクトの継続的な発展に合わせて更新していく生きた文書として管理されます。