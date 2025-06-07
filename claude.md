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

## GCP エミュレータ開発環境

### エミュレータの概要
開発・テスト時は実際のGCPサービスではなく、ローカルエミュレータを使用することを **強く推奨** します。

- **Firestore エミュレータ**: データベース操作のテスト・開発
- **GCS エミュレータ**: ファイルストレージ操作のテスト・開発
- **コスト削減**: 実際のGCPリソースを使用しないため課金なし
- **高速**: ローカル実行のため応答が高速
- **独立性**: 本番環境に影響を与えない

### 前提条件

#### Firestore エミュレータ
```bash
# Google Cloud SDK のインストール確認
gcloud --version

# Beta コンポーネントのインストール（必要な場合）
gcloud components install beta
```

#### GCS エミュレータ
```bash
# Docker のインストール確認
docker --version

# Dockerデーモンの動作確認
docker info

# エミュレータイメージの事前取得（推奨）
docker pull fsouza/fake-gcs-server:latest
```

### エミュレータの起動方法

#### 自動起動（推奨）
```bash
# プロジェクトルートから実行
python tests/app/gcp_emulator_run.py

# 初期データ付きで起動
python tests/app/gcp_emulator_run.py --init-data
```

#### 手動起動
```bash
# Firestore エミュレータ（ポート8081）
gcloud beta emulators firestore start --host-port=localhost:8081

# GCS エミュレータ（ポート9000、別ターミナル）
docker run -d --rm --name fake-gcs-server \
  -p 9000:9000 \
  fsouza/fake-gcs-server:latest \
  -scheme http -host 0.0.0.0 -port 9000
```

### 環境変数の設定
エミュレータ使用時は以下の環境変数を設定：

```bash
# Firestore エミュレータ
export FIRESTORE_EMULATOR_HOST=localhost:8081

# GCS エミュレータ  
export STORAGE_EMULATOR_HOST=http://localhost:9000
export GCS_EMULATOR_HOST=http://localhost:9000
export GOOGLE_CLOUD_PROJECT=your-test-project-id

# デバッグ用（オプション）
export DEBUG=1
```

### エミュレータ接続確認
```bash
# Firestore エミュレータの動作確認
curl http://localhost:8081

# GCS エミュレータの動作確認  
curl http://localhost:9000/_internal/healthcheck
```

### 開発時の使用パターン

#### パターン1: 常時エミュレータ使用（推奨）
```bash
# エミュレータを起動（別ターミナル）
python tests/app/gcp_emulator_run.py

# 開発サーバー起動
cd backend && python -m app.main
cd frontend && npm run dev
```

#### パターン2: テスト時のみエミュレータ使用
```bash
# テスト実行前にエミュレータ起動
python tests/app/gcp_emulator_run.py &

# テスト実行
pytest tests/app/ -v

# エミュレータ停止
pkill -f gcp_emulator_run.py
```

## コーディングルール
- **Python**: Black フォーマット, 型ヒント必須, `common_utils.logger` 使用
- **TypeScript**: ESLint準拠, 関数コンポーネント + Hooks, Tailwind CSS のみ
- **Git**: 日本語コミットメッセージ, 実際のコミットは禁止（メッセージのみ出力）

## 主な機能
1. **AI チャット**: Gemini モデルによるマルチモーダルチャット
2. **画像生成**: Imagen による AI 画像生成
3. **音声文字起こし**: リアルタイム + Whisper バッチ処理（話者分離付き）
4. **位置情報**: Google Maps API による住所検索・地図表示

## テスト戦略とガイドライン

### テストフレームワーク
- **メインフレームワーク**: pytest（高度な機能とプラグイン活用）
- **サブフレームワーク**: unittest（標準ライブラリ、レガシーコード対応）

### テスト環境とエミュレータ使用

#### テストレベル別のエミュレータ使用方針
1. **Unit Tests**: モック使用（高速・独立性重視）
2. **Integration Tests**: エミュレータ使用（実環境に近い動作確認）
3. **E2E Tests**: 実際のGCP環境使用（本番環境での動作確認）

#### エミュレータテストの実行
```bash
# エミュレータ利用可能性の確認
pytest tests/app/test_emulator_availability.py -v

# 通常のテスト（モックベース）
pytest tests/app/ -m "not emulator" -v

# エミュレータ統合テスト
pytest tests/app/ -m emulator -v

# 全てのテスト（エミュレータ込み）
python tests/app/gcp_emulator_run.py &  # エミュレータ起動
pytest tests/app/ -v                    # 全テスト実行
```

### テスト命名規約
```python
# 関数形式
def test_関数・メソッド名_仕様():
    # テスト実装

# クラス形式  
class TestClassName:
    def test_メソッド名_仕様():
        # テスト実装
```

### テスト構成
```
tests/
├── app/                           # アプリケーションテスト
│   ├── test_emulator_availability.py  # エミュレータ利用可能性テスト
│   ├── test_whisper_emulator_example.py # エミュレータ使用例
│   ├── gcp_emulator_run.py        # エミュレータ起動スクリプト
│   └── ...
├── requirements.txt               # テスト用依存関係
├── conftest.py                   # pytest設定・フィクスチャ
└── pytest.ini                   # pytest設定ファイル
```

### 推奨pytestオプション
```bash
pytest -vv --tb=short -s                    # 詳細出力＋短縮トレースバック
pytest -k "pattern"                         # パターンマッチテスト実行
pytest --pdb                                # 失敗時デバッガ起動
pytest tests/app/test_specific.py::test_func # 特定テスト実行
```

### テストベストプラクティス
1. **AAA パターン**: Arrange（準備） → Act（実行） → Assert（検証）
2. **mockは最小限**: 実環境に近い状態でテスト、autospecで引数チェック
3. **parametrize活用**: 複数テストデータを1つのテスト関数で処理
4. **フィクスチャ**: 共通セットアップ・クリーンアップロジックの再利用
5. **マーカー**: テストスキップ・カテゴリ分け・条件付き実行
6. **エミュレータ優先**: FirestoreとGCS操作はエミュレータを優先使用
7. **環境分離**: テスト用プロジェクトIDで本番環境を保護

### エミュレータテストのベストプラクティス
```python
# エミュレータ使用テストの例
@pytest.mark.emulator
class TestWithEmulator:
    def test_firestore_integration(self, real_firestore_client):
        # 実際のFirestoreエミュレータを使用
        collection = real_firestore_client.collection('test_collection')
        doc_ref = collection.document('test_doc')
        doc_ref.set({'key': 'value'})
        
        # データが正しく保存されたことを確認
        assert doc_ref.get().to_dict()['key'] == 'value'
```

### 推奨プラグイン
- **pytest-mock**: モック機能の強化
- **pytest-clarity**: テスト失敗時の差分ハイライト表示
- **pytest-randomly**: テスト実行順序のランダム化
- **pytest-freezegun**: 時間固定テスト

## トラブルシューティング

### 一般的な問題
- **認証エラー**: Firebase 設定・サービスアカウント確認
- **CORS エラー**: `ORIGINS` 環境変数確認  
- **音声エラー**: ffmpeg インストール・CUDA 環境確認
- **デバッグ**: `DEBUG=1` 環境変数でログ詳細化
- **テスト失敗**: `pytest --pdb` でデバッガ起動、`breakpoint()` でブレークポイント設定

### GCP エミュレータ関連の問題

#### Firestore エミュレータ
```bash
# エミュレータが起動しない場合
gcloud auth list                    # 認証状態確認
gcloud components install beta     # Beta コンポーネント再インストール
netstat -tulpn | grep 8081        # ポート競合確認

# エミュレータ環境変数の確認
echo $FIRESTORE_EMULATOR_HOST      # localhost:8081 であることを確認
```

#### GCS エミュレータ
```bash
# Docker関連の問題
docker info                        # Dockerデーモン状態確認
docker ps -a | grep fake-gcs       # 既存コンテナ確認
docker rm -f fake-gcs-server       # 古いコンテナ削除

# ポート競合の解決
lsof -i :9000                      # ポート9000使用状況確認
docker stop $(docker ps -q --filter publish=9000)  # ポート使用中コンテナ停止
```

#### 環境変数の問題
```bash
# 環境変数が正しく設定されているか確認
printenv | grep EMULATOR
printenv | grep GCS

# 環境変数をリセット
unset FIRESTORE_EMULATOR_HOST
unset STORAGE_EMULATOR_HOST
unset GCS_EMULATOR_HOST

# エミュレータを再起動
python tests/app/gcp_emulator_run.py
```

#### テスト実行時の問題
```bash
# エミュレータ依存関係エラー
pytest tests/app/test_emulator_availability.py -v  # 依存関係確認

# Docker未インストール時
# → GCSエミュレータテストは自動的にスキップされます

# gcloud未インストール時  
# → Firestoreエミュレータテストは自動的にスキップされます
```

#### パフォーマンス問題
```bash
# エミュレータ起動が遅い場合
docker pull fsouza/fake-gcs-server:latest  # 最新イメージを事前取得

# メモリ不足の場合
docker system prune -f             # 不要なDockerリソース削除
```

## ナレッジ管理とコンテキスト保存

### 作業記録の保存方法
重要な作業完了時は `./ContextSave/` に結果を保存すること。以下の形式に従う：

#### 保存タイミング
- 大きなバグ修正完了時
- テスト環境の大幅改善時
- 新機能実装完了時
- トラブルシューティングの知見蓄積時

#### ファイル命名規則
```
./ContextSave/[作業内容]_[yyyyMMdd]_[HHmmss].md
```

#### 必須セクション構成
1. **# Objective** - プロジェクトとタスクの目的
2. **# All user instructions** - ユーザーからの全指示内容
3. **# Current status of the task** - 達成済み内容（残課題は含めない）
4. **# Pending issues with snippets** - 残課題とエラー詳細（解決策は含めない）
5. **# Build and development instructions** - ビルド・実行・テスト手順
6. **# Relevant file paths** - 関連ファイルパス一覧

#### 実行例
```bash
# テスト改善完了時の保存例
echo "Whisperテスト改善完了レポート" > ./ContextSave/whisper_test_improvement_20250607_110204.md
```

### 参考ファイル
- `./.claude/KnowledgeTransfer.txt` - 保存形式の詳細ガイド
- 過去の保存例: `./ContextSave/` 内の既存ファイル

### 重要事項
- **詳細記録**: エラーログ、コードスニペット、実行結果を可能な限り詳細に記録
- **再現可能性**: 他の人が同じ作業を再現できるレベルの情報を含める
- **技術的洞察**: 解決に至った重要な技術的発見や知見を明記

## コミットメッセージ出力

### 作業完了時のコミットメッセージ
**すべての作業完了時は、変更内容に係る日本語のコミットメッセージを必ず出力すること。**

#### コミットメッセージの要件
- **言語**: 日本語で記述
- **形式**: 簡潔で分かりやすい要約 + 詳細な変更内容
- **内容**: 実際の変更内容を正確に反映
- **注意**: 実際のコミットは実行しない（メッセージ出力のみ）

#### コミットメッセージの構成例
```
[分類]：[要約（50文字以内）]

- [変更内容1の詳細]
- [変更内容2の詳細]  
- [変更内容3の詳細]

[追加の説明や影響範囲]
```

#### 分類の例
- **機能追加** - 新機能の実装
- **バグ修正** - 不具合の修正
- **改善** - 既存機能の改善・最適化
- **テスト** - テストコードの追加・修正
- **ドキュメント** - ドキュメントの更新
- **リファクタリング** - コード構造の改善
- **設定** - 設定ファイルの変更
- **環境構築** - 開発環境の構築・改善

#### 実際の出力例
```
テスト：GCPエミュレータ利用可能性チェック機能を追加

- tests/app/test_emulator_availability.py 新規作成
- conftest.py のエミュレータフィクスチャ改善
- README.md にエミュレータテスト実行方法を追加

開発・テスト環境でのFirestore/GCSエミュレータの
利用可能性を事前チェックできるようになりました。
```

### 重要な注意事項
- **必須**: 作業完了時は必ずコミットメッセージを出力する
- **禁止**: 実際の `git commit` コマンドは実行しない
- **目的**: 変更履歴の記録と作業内容の明確化