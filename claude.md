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

### ユニットテストの基本原則

#### 「1単位の振る舞い」の識別
- **ユニットテストは1単位の振る舞い（a unit of Behavior）を検証すること**
- 大きな振る舞いは分割して統治する（Divide and Conquer）
- 処理フローロジックと中核ロジックを分離する

#### 振る舞い分割の戦略
```python
# ❌ 悪い例：大きすぎる振る舞い（トランザクションスクリプト）
def test_movie_ticket_price_calculation_all_patterns():
    # 顧客分類、日付、会員フラグ、クーポンを全て組み合わせたテスト
    # → 384ケースの組み合わせが必要、テスト設計が困難
    pass

# ✅ 良い例：小さく分割された振る舞い
class TestRegularPriceCalculation:
    """通常料金計算の振る舞いをテスト"""
    def test_get_regular_price_大人の場合2000円を返すこと(self):
        pass
    
    def test_get_regular_price_シニアの場合1500円を返すこと(self):
        pass

class TestDiscountPriceCalculation:
    """割引料金計算の振る舞いをテスト"""
    def test_find_cheapest_discount_水曜日割引が適用されること(self):
        pass

class TestFinalPriceCalculation:
    """最終料金決定の振る舞いをテスト"""
    def test_determine_final_price_クーポンが最安の場合クーポン料金を返すこと(self):
        pass
```

### テストコードのSOS原則

#### S - 構造化されている（Structured）
```python
# パッケージ構造：垂直分割（業務観点）で設計
tests/
├── chat/                    # チャット機能
│   ├── test_message_handling.py
│   └── test_ai_integration.py
├── whisper/                 # 音声文字起こし機能
│   ├── test_audio_processing.py
│   └── test_batch_processing.py
└── auth/                    # 認証機能
    ├── test_firebase_auth.py
    └── test_token_validation.py

# テストケースの階層化（pytest内部クラス使用）
class TestWhisperAPI:
    """Whisper API のテスト"""
    
    class TestNormalCases:
        """正常系テスト"""
        def test_process_audio_有効なWAVファイルで文字起こし成功(self):
            pass
    
    class TestErrorCases:
        """異常系テスト"""
        def test_process_audio_無効なファイル形式で400エラー(self):
            pass
    
    class TestPerformance:
        """性能テスト"""
        def test_process_audio_5分音声が30秒以内で処理完了(self):
            pass
```

#### O - 整理されている（Organized）
```python
# テスト設計の根拠をdocstringで明記
class TestAudioFormatValidation:
    """
    音声ファイル形式検証のテスト
    
    テスト設計の根拠：
    - 同値分割：有効形式（wav, mp3, m4a）vs 無効形式（txt, jpg等）
    - 境界値分析：ファイルサイズ上限（100MB）付近
    - エラー推測：拡張子と実際の形式が異なるケース
    """
    
    @pytest.mark.parametrize(
        ["file_format", "expected_result"],
        [
            ("wav", True),
            ("mp3", True), 
            ("m4a", True),
            ("txt", False),
            ("jpg", False),
        ],
        ids=[
            "WAV形式_有効",
            "MP3形式_有効",
            "M4A形式_有効", 
            "テキスト形式_無効",
            "画像形式_無効",
        ],
    )
    def test_validate_audio_format_各形式の検証結果が正しいこと(
        self, file_format, expected_result
    ):
        pass
```

#### D - 自己文書化されている（Self-documenting）
```python
# AAA（Arrange-Act-Assert）パターンの徹底
def test_whisper_batch_job_正常なパラメータで処理開始されること(self):
    """Whisperバッチジョブが正常なパラメータで開始されることを検証"""
    # Arrange（準備）
    audio_file_path = "gs://bucket/test_audio.wav"
    job_config = WhisperJobConfig(
        language="ja",
        speaker_diarization=True,
        model="large-v3"
    )
    
    # Act（実行）
    result = whisper_service.start_batch_job(audio_file_path, job_config)
    
    # Assert（検証）
    assert result.status == "SUBMITTED"
    assert result.job_id is not None
    assert result.estimated_completion_time > datetime.now()
```

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
# 関数形式：条件と期待する振る舞いを明示
def test_関数名_条件_期待する振る舞い():
    # テスト実装

# クラス形式：業務的な振る舞い単位でグループ化
class TestClassName:
    def test_メソッド名_条件_期待する振る舞い(self):
        # テスト実装

# 具体例
def test_calculate_movie_ticket_price_大人平日_通常料金2000円を返すこと(self):
    pass

def test_validate_audio_file_サイズ100MB超過_ValidationErrorを発生させること(self):
    pass
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

#### 質の良いテストの必要性
**「単にテストを作成すれば十分ということではありません。作成されたテストの質が悪ければ、テストを全くしない場合と同じ結果になる」**

#### 実践すべき原則
1. **振る舞い駆動設計**: 実装の詳細ではなく、外部から観察可能な振る舞いをテスト
2. **AAA パターン**: Arrange（準備） → Act（実行） → Assert（検証）
3. **テスト容易性の重視**: 「テストしやすい設計」を意識したアーキテクチャ
4. **parametrize活用**: 複数テストデータを1つのテスト関数で処理
5. **フィクスチャ**: 共通セットアップ・クリーンアップロジックの再利用
6. **マーカー**: テストスキップ・カテゴリ分け・条件付き実行
7. **エミュレータ優先**: FirestoreとGCS操作はエミュレータを優先使用
8. **環境分離**: テスト用プロジェクトIDで本番環境を保護
9. **テストダブル最小化**: まず実オブジェクトでのテストを検討

#### テスト容易性（Testability）の観点
```python
# ❌ テストしにくい設計例
class AudioProcessor:
    def process_file(self, file_path: str) -> str:
        # ファイル読み込み、処理、保存が一体化
        audio_data = self._read_file(file_path)
        processed = self._apply_noise_reduction(audio_data)
        processed = self._normalize_volume(processed)
        output_path = f"/tmp/processed_{uuid4()}.wav"
        self._save_file(processed, output_path)
        return output_path
        
# ✅ テストしやすい設計例  
class AudioProcessor:
    def process_audio_data(self, audio_data: AudioData) -> AudioData:
        """純粋な処理ロジック（副作用なし）"""
        processed = self._apply_noise_reduction(audio_data)
        return self._normalize_volume(processed)

class AudioFileHandler:
    def __init__(self, processor: AudioProcessor):
        self.processor = processor
        
    def process_file(self, file_path: str, output_path: str) -> None:
        """ファイルI/Oと処理の分離"""
        audio_data = self._read_file(file_path)
        processed = self.processor.process_audio_data(audio_data)
        self._save_file(processed, output_path)
```

### テストダブル利用の基本方針

#### **テストダブル利用指針（優先順位）**

1. **まず、テストダブルを使わずに済むか考える**
2. **スタブは目的を理解した上で適切に使えばOK**  
3. **モックの利用は極めて慎重に**

```python
# ✅ 最優先：テストダブルなしでテスト
def test_price_calculator_通常料金計算_テストダブルなし(self):
    calculator = PriceCalculator()
    result = calculator.calculate_regular_price(CustomerType.ADULT)
    assert result == 2000

# ✅ 必要に応じてスタブ使用
def test_external_api_call_ネットワークエラー時の動作確認(self):
    # 外部API呼び出しの制御にスタブを使用
    with patch('external_api.get_exchange_rate') as stub_api:
        stub_api.return_value = 110.0  # 間接入力の制御
        
        result = currency_converter.convert(100, 'USD', 'JPY')
        assert result == 11000

# ⚠️ 慎重に使用：モック（間接出力の観測）
def test_notification_service_メール送信が実行されること(self):
    # 本当に観測すべきか？副作用をなくす設計は可能か？を検討済み
    with patch('email_service.send_email') as mock_email:
        notification_service.notify_user("user@example.com", "メッセージ")
        
        # 外部との契約として観察可能な振る舞いのみ検証
        mock_email.assert_called_once_with(
            to="user@example.com",
            subject="通知",
            body="メッセージ"
        )
```

### モック設計の実装ガイドライン

#### **create_autospec() + side_effect パターンの使用**

**このプロジェクトでは、テストダブルが必要な場合に `create_autospec() + side_effect` パターンを推奨します。**

```python
from unittest.mock import create_autospec, patch
import google.cloud.storage as storage

# ✅ 推奨パターン: create_autospec + side_effect
def test_gcs_operations():
    # 実際のクラスからautospecを作成
    mock_client_class = create_autospec(storage.Client, spec_set=True)
    
    # カスタム振る舞いを定義
    class GCSClientBehavior:
        def __init__(self):
            self._buckets = {}
        
        def bucket(self, name: str):
            if not isinstance(name, str) or not name:
                raise ValueError("バケット名は空文字列にできません")
            if name not in self._buckets:
                self._buckets[name] = GCSBucketBehavior(name)
            return self._buckets[name]
    
    # autospecモックにカスタム振る舞いを注入
    behavior = GCSClientBehavior()
    mock_client_instance = mock_client_class.return_value
    mock_client_instance.bucket.side_effect = behavior.bucket
    
    with patch('google.cloud.storage.Client', return_value=mock_client_instance):
        # テスト実行
        client = storage.Client()
        
        # ✅ 存在するメソッドのみ呼び出し可能（autospecの安全性）
        bucket = client.bucket("test-bucket")
        
        # ✅ カスタム振る舞い（状態管理）が動作
        assert bucket.name == "test-bucket"
        
        # ❌ 存在しないメソッドは呼び出せない（autospecの保護）
        # client.non_existent_method()  # ← AttributeError
```

#### **なぜこのパターンが推奨されるのか**

1. **型安全性**: 実際のクラス構造に基づくため、存在しないメソッドの呼び出しを防ぐ
2. **柔軟性**: side_effectでカスタムロジック（状態管理・バリデーション）を実装可能
3. **保守性**: 実際のAPIが変更されたときにテストで検出できる
4. **デバッグ性**: エラーが発生したときに原因が明確

#### **禁止パターン**

```python
# ❌ 禁止: autospec + return_value の併用
with patch('module.Class', return_value=mock_obj, autospec=True):
    # InvalidSpecError が発生

# ❌ 非推奨: MagicMock のみ使用
with patch('module.Class') as mock:
    mock.return_value = MagicMock()
    # 存在しないメソッドも呼び出せてしまう

# ❌ 非推奨: plain patch のみ
with patch('module.function', return_value="test"):
    # 引数チェックが行われない
```

#### **実装ガイドライン**

```python
# ✅ 基本パターン
mock_class = create_autospec(OriginalClass, spec_set=True)
mock_instance = mock_class.return_value
mock_instance.method.side_effect = custom_function

# ✅ 複雑な状態管理が必要な場合
class CustomBehavior:
    def __init__(self):
        self.state = {}
    
    def method(self, arg):
        # カスタムロジック
        return self.handle_method(arg)

behavior = CustomBehavior()
mock_instance.method.side_effect = behavior.method

# ✅ エラーパターンのテスト
def error_side_effect(*args, **kwargs):
    raise ConnectionError("テスト用エラー")

mock_instance.method.side_effect = error_side_effect
```

#### **適用対象**

- **全てのGCPクライアント**: Firestore, Cloud Storage, Vertex AI等
- **外部ライブラリ**: pandas, numpy, requests等
- **カスタムクラス**: プロジェクト内の重要なクラス
- **関数モック**: 重要なビジネスロジック関数

この設計により、テストの**安全性・保守性・拡張性**が大幅に向上し、本番環境での不具合を事前に検出できます。

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
作業完了時は `./ContextSave/` に結果を保存すること。以下の形式に従う：

#### 保存タイミング
- 大きなバグ修正完了時
- テスト環境の大幅改善時
- 新機能実装完了時
- トラブルシューティングの知見蓄積時

#### ファイル命名規則（統一済み）
**2025年6月8日より、すべてのContextSaveファイルおよびプロジェクトガイドラインファイルは以下の形式で統一**

```
./ContextSave/{作業内容}_{yyyyMMdd}_{HHmmss}.md
```

**例**：
- `whisper_test_improvement_20250607_174029.md`
- `firebase_auth_fix_20250607_201028.md`
- `project_guidelines_20250608_040815.md`

#### 命名規則のポイント
- **作業内容**: 英語の小文字とアンダースコアで構成
- **日付**: yyyyMMdd形式（例：20250607）
- **時刻**: HHmmss形式（例：174029）
- **拡張子**: 常に.md
- **区切り文字**: アンダースコア（_）で統一

#### 必須セクション構成
1. **# Objective** - プロジェクトとタスクの目的
2. **# All user instructions** - ユーザーからの全指示内容
3. **# Current status of the task** - 達成済み内容（残課題は含めない）
4. **# Pending issues with snippets** - 残課題とエラー詳細（解決策は含めない）
5. **# Build and development instructions** - ビルド・実行・テスト手順
6. **# Relevant file paths** - 関連ファイルパス一覧

#### 実行例
```bash
# テスト改善完了時の保存例（新形式）
echo "Whisperテスト改善完了レポート" > ./ContextSave/whisper_test_improvement_20250607_110204.md
```

### 参考ファイル
- `./.claude/KnowledgeTransfer.txt` - 保存形式の詳細ガイド
- 過去の保存例: `./ContextSave/` 内の既存ファイルのうち、最近の（created_atが最新の）ファイルを参照

### 重要事項
- **詳細記録**: エラーログ、コードスニペット、実行結果を可能な限り詳細に記録
- **再現可能性**: 他の人が同じ作業を再現できるレベルの情報を含める
- **技術的洞察**: 解決に至った重要な技術的発見や知見を明記
- **命名規則遵守**: 必ず統一された形式でファイル名を作成する

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
