# Objective

Whisperテストファイルの品質向上プロジェクト。具体的には、`./tests/app`ディレクトリ内のテストファイルにおいて、`autospec=True`が未設定のモック使用箇所の特定・修正と、GCPエミュレータ（`./common_utils/gcp_emulator.py`）を活用していないFirestore/GCSテストの段階的移行を実施。

# All user instructions

```
Please examine the tests within the ./tests/app directory. For any tests that haven't been investigated with auto_spec=true, please set it to true. Additionally, for any tests related to GCP's Firestore or GCS that are not currently using ./common_utils/gcp_emulator.py, gradually replace them with tests that do. Ultrathinking!!
```

# Current status of the task

## ✅ 完了した作業

### 1. テストファイル全体の調査と分析
- `./tests/app`ディレクトリ内の全テストファイルを詳細に検査
- 8つのメインテストファイルを分析：
  - `test_simple.py`
  - `test_whisper_api.py` 
  - `test_whisper_api_enhanced.py`
  - `test_whisper_batch.py`
  - `test_whisper_combine.py`
  - `test_whisper_diarize.py`
  - `test_whisper_integration.py`
  - `test_whisper_transcribe.py`

### 2. autospec=True の未設定箇所の特定と修正

#### 修正したファイル：
- **test_simple.py**
  ```python
  # Before
  from unittest.mock import patch, Mock
  @patch('os.path.exists')
  
  # After  
  from unittest.mock import patch, Mock, create_autospec
  @patch('os.path.exists', autospec=True)
  ```

- **test_whisper_api.py**
  ```python
  # 主要なGCPクライアントモックにautospec=True追加
  patch("google.cloud.storage.Client", autospec=True)
  patch("google.cloud.firestore.Client", autospec=True)
  patch("backend.app.api.whisper.enqueue_job_atomic", autospec=True)
  patch("fastapi.BackgroundTasks.add_task", autospec=True)
  ```

- **test_whisper_batch.py**
  ```python
  # Whisper処理関数とGCPクライアントにautospec追加
  patch("google.cloud.storage.Client", return_value=mock_gcs_client, autospec=True)
  patch("whisper_batch.app.transcribe.transcribe_audio", side_effect=mock_transcribe_audio, autospec=True)
  patch("whisper_batch.app.main.create_single_speaker_json", side_effect=mock_create_single_speaker_json, autospec=True)
  patch("google.cloud.firestore.transactional", side_effect=mock_transactional_decorator, autospec=True)
  ```

- **test_whisper_transcribe.py**
  ```python
  # Whisperモデルとデータ保存関数にautospec追加
  patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model, autospec=True)
  patch("whisper_batch.app.transcribe.save_dataframe", autospec=True)
  patch("google.cloud.storage.Client", autospec=True)
  ```

- **test_whisper_diarize.py**
  ```python
  # 話者分離パイプラインにautospec追加
  patch("whisper_batch.app.diarize.Pipeline", autospec=True)
  patch("whisper_batch.app.diarize.save_dataframe", autospec=True)
  ```

### 3. GCPエミュレータ統合の実装

#### 新規作成ファイル：
- **test_whisper_emulator_example.py**
  - 完全なGCPエミュレータ使用例を提供
  - Firestore/GCS両方のエミュレータ使用パターンを網羅
  - 実際のGCPクライアントとエミュレータの統合例
  - モックフォールバック機能付き

#### conftest.py の拡張：
```python
# 新規追加フィクスチャ
@pytest.fixture(scope="session")
def emulator_firestore():
    """Firestoreエミュレータのセッションスコープフィクスチャ"""
    
@pytest.fixture(scope="session") 
def emulator_gcs():
    """GCSエミュレータのセッションスコープフィクスチャ"""
    
@pytest.fixture
def real_firestore_client(emulator_firestore):
    """実際のFirestoreクライアント（エミュレータ接続）"""
    
@pytest.fixture
def real_gcs_client(emulator_gcs):
    """実際のGCSクライアント（エミュレータ接続）"""
```

#### test_whisper_api.py への統合例追加：
```python
@pytest.mark.emulator
class TestWhisperJobOperationsWithEmulator:
    """GCPエミュレータを使用したジョブ操作テスト（使用例）"""
    
    @pytest.mark.asyncio
    async def test_job_storage_with_real_firestore_emulator(self, real_firestore_client, mock_auth_user):
        # 実際のFirestoreクライアント使用例
        
    @pytest.mark.asyncio
    async def test_file_storage_with_real_gcs_emulator(self, real_gcs_client):
        # 実際のGCSクライアント使用例
```

### 4. 段階的移行戦略の確立

#### アプローチ：
1. **既存テスト保持** - モックベースのテストは引き続き動作（autospec改善済み）
2. **新規エミュレータフィクスチャ** - より現実的なGCP動作が必要な場合に使用可能
3. **サンプル実装** - 将来のテスト開発のためのベストプラクティス例
4. **エラーハンドリング** - エミュレータが利用できない環境での適切なスキップ処理

## 技術的改善効果

### autospec=True の導入効果：
- **引数検証強化** - 実際の関数シグネチャに基づく厳密なチェック
- **API変更検出** - インターフェース変更時の早期発見
- **より現実的なモック動作** - 実際の実装に近い挙動

### GCPエミュレータ統合効果：
- **統合テスト品質向上** - 実際のGCP APIに近い環境でのテスト
- **データ整合性テスト** - Firestore/GCS間の実際のデータフロー検証
- **本番環境類似性** - エミュレータによる本番に近い条件でのテスト

# Build and development instructions

## テスト実行方法

### 通常のテスト実行（改善されたモック使用）
```bash
# 基本テスト実行
pytest tests/app/

# 詳細出力
pytest tests/app/ -vv --tb=short

# 特定ファイルのみ
pytest tests/app/test_whisper_api.py
```

### エミュレータを使用したテスト実行
```bash
# エミュレータテストのみ実行（要Docker/gcloud）
pytest tests/app/ -m emulator

# エミュレータ例ファイルの実行
pytest tests/app/test_whisper_emulator_example.py --disable-warnings

# 特定のエミュレータテスト
pytest tests/app/test_whisper_api.py::TestWhisperJobOperationsWithEmulator -s
```

### 環境要件
```bash
# 基本テスト（モックベース）
pip install pytest pytest-asyncio

# エミュレータテスト（追加要件）
pip install google-cloud-firestore google-cloud-storage
# Docker（GCSエミュレータ用）
# gcloud CLI（Firestoreエミュレータ用）
```

## 新規テスト開発ガイドライン

### autospec使用パターン
```python
# ✅ 推奨
from unittest.mock import patch, Mock, create_autospec

@patch('module.function', autospec=True)
def test_function(mock_func):
    pass

# ✅ 推奨  
with patch('google.cloud.storage.Client', autospec=True) as mock_client:
    pass
```

### エミュレータ使用パターン
```python
# ✅ 推奨 - セッションフィクスチャ使用
def test_with_emulator(real_firestore_client):
    client = real_firestore_client
    # 実際のFirestore操作

# ✅ 推奨 - 直接エミュレータ使用
@pytest.mark.asyncio
async def test_direct_emulator():
    with firestore_emulator_context(port=8091) as emulator:
        client = firestore.Client(project='test-project')
        # テスト実装
```

# Relevant file paths

## 修正したファイル
- `/tests/app/test_simple.py` - autospec追加、create_autospecインポート
- `/tests/app/test_whisper_api.py` - 複数のautospec追加、エミュレータ統合例追加
- `/tests/app/test_whisper_batch.py` - GCP/Whisper関数へのautospec追加
- `/tests/app/test_whisper_transcribe.py` - Whisperモデル関連autospec追加  
- `/tests/app/test_whisper_diarize.py` - Pipeline関連autospec追加
- `/tests/app/conftest.py` - エミュレータフィクスチャ追加

## 新規作成ファイル
- `/tests/app/test_whisper_emulator_example.py` - GCPエミュレータ使用の完全な例

## 参照先ファイル
- `/common_utils/gcp_emulator.py` - エミュレータ実装（FirestoreEmulator, GCSEmulator）
- `/common_utils/class_types.py` - Whisperデータ型定義
- `/backend/app/api/whisper.py` - Whisper API実装
- `/whisper_batch/app/` - バッチ処理実装ディレクトリ

## 実行コマンド履歴
```bash
# 分析フェーズ
ls tests/app/
cat tests/app/test_simple.py
cat tests/app/test_whisper_api.py
# ... 他テストファイル

# 修正フェーズ  
# test_simple.pyの修正
# test_whisper_api.pyの修正
# test_whisper_batch.pyの修正
# test_whisper_transcribe.pyの修正
# test_whisper_diarize.pyの修正

# 新規作成フェーズ
# test_whisper_emulator_example.py作成
# conftest.py拡張
```

## 今後の推奨事項

1. **新規テスト作成時** - `test_whisper_emulator_example.py`のパターンを参考
2. **既存テスト拡張時** - autospec=Trueの一貫した使用
3. **統合テスト開発時** - エミュレータフィクスチャの活用
4. **CI/CD統合時** - エミュレータテストの条件付き実行設定