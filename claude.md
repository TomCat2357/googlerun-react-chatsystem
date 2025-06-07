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

## テスト戦略とガイドライン

### テストフレームワーク
- **メインフレームワーク**: pytest（高度な機能とプラグイン活用）
- **サブフレームワーク**: unittest（標準ライブラリ、レガシーコード対応）

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
├── app/                    # アプリケーションテスト
├── requirements.txt        # テスト用依存関係
├── conftest.py            # pytest設定・フィクスチャ
└── pytest.ini            # pytest設定ファイル
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

### 推奨プラグイン
- **pytest-mock**: モック機能の強化
- **pytest-clarity**: テスト失敗時の差分ハイライト表示
- **pytest-randomly**: テスト実行順序のランダム化
- **pytest-freezegun**: 時間固定テスト

## トラブルシューティング
- **認証エラー**: Firebase 設定・サービスアカウント確認
- **CORS エラー**: `ORIGINS` 環境変数確認  
- **音声エラー**: ffmpeg インストール・CUDA 環境確認
- **デバッグ**: `DEBUG=1` 環境変数でログ詳細化
- **テスト失敗**: `pytest --pdb` でデバッガ起動、`breakpoint()` でブレークポイント設定

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