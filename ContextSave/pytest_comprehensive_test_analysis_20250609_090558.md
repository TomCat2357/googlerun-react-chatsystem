# Objective

プロジェクトのテスト環境の包括的な実行・管理・分析を実施し、ユニットテストの基本原則（1単位の振る舞い識別、テストコードのSOS原則）を適用したテスト戦略の実践と問題点の特定・改善を行う。

# All user instructions

## 主要指示内容
1. **プロジェクトテストの実行・管理**: `project:test ultrathinking` コマンドによる包括的テスト管理
2. **ユニットテスト基本原則の適用**: 「1単位の振る舞い」識別による適切なテスト分割
3. **テストコードSOS原則の実践**: 
   - **S (Structured)**: 階層化されたテストクラス構造
   - **O (Organized)**: テスト設計根拠の明記とパラメータテスト活用
   - **D (Self-documenting)**: AAA パターンと自己文書化
4. **create_autospec + side_effect パターン適用**: テストダブル設計の安全性確保
5. **GCPエミュレータ統合**: Firestore・GCS エミュレータを活用した統合テスト
6. **テスト結果分析**: カバレッジ測定とパフォーマンス分析

## 詳細要件
- pytest実行時の推奨オプション: `-vv --tb=short -s`
- エミュレータ環境変数設定の徹底
- テスト命名規約: `test_関数名_条件_期待する振る舞い`
- テストダブル優先順位: (1)テストダブルなし → (2)スタブ → (3)モック(慎重に)

# Current status of the task

## ✅ 完了済み項目

### 1. テスト環境構築・検証
- **Python環境**: Python 3.11.12 + pytest 8.3.4 確認済み
- **依存関係**: tests/requirements.txt の全パッケージ正常インストール確認
- **仮想環境**: `.venv` 環境での実行基盤確立

### 2. GCPエミュレータ環境の確立
- **Firestore エミュレータ**: localhost:8081 で正常動作確認
- **GCS エミュレータ**: Docker基盤（localhost:9000）で正常動作確認
- **環境変数設定**: 以下の環境変数を適切に設定済み
  ```bash
  FIRESTORE_EMULATOR_HOST=localhost:8081
  STORAGE_EMULATOR_HOST=http://localhost:9000
  GCS_EMULATOR_HOST=http://localhost:9000
  GOOGLE_CLOUD_PROJECT=supportaisystem20250412
  DEBUG=1
  ENVIRONMENT=test
  FRONTEND_PATH=/tmp/frontend
  ```

### 3. 基本テスト実行成功
- **test_simple.py**: 7/7テスト成功（100%成功率）
  - 環境変数テスト
  - 基本数学関数テスト
  - 非同期関数テスト
  - クラスメソッドテスト
  - モック機能テスト
- **test_emulator_availability.py**: 14/20テスト成功（70%成功率）
  - エミュレータ機能テスト
  - 依存関係確認テスト
  - 互換性テスト

### 4. 初期問題の解決
- **VALID_STATUSES エラー**: `backend/app/api/whisper.py:58` のAttributeError解決
  ```python
  # 修正前
  VALID_STATUSES = set(WhisperFirestoreData.VALID_STATUSES)
  
  # 修正後
  VALID_STATUSES = {"queued", "launched", "processing", "completed", "failed", "canceled"}
  ```
- **GeocodeRequest エラー**: `backend/app/api/geocoding.py:11` のインポート名修正
  ```python
  # 修正前
  from common_utils.class_types import GeocodeRequest
  
  # 修正後  
  from common_utils.class_types import GeocodingRequest
  ```
- **静的ファイルパスエラー**: `/tmp/frontend/assets` ディレクトリ作成とassets配置

### 5. テスト戦略の実践確認
- **階層化テスト構造**: pytest内部クラスによる正常系・異常系・境界値テストの分離確認
- **パラメータテスト**: `@pytest.mark.parametrize` の適切な活用確認
- **AAA パターン**: Arrange-Act-Assert 構造の実装確認
- **日本語テスト名**: 条件と期待する振る舞いを明示したテスト命名の実践確認

# Pending issues with snippets

## 🔴 高優先度問題

### 1. Pydantic v2 フィールドアクセス問題（最重要）

**症状**: 
```
AttributeError: 'WhisperJobData' object has no attribute 'job_id'
```

**影響範囲**: Whisper関連テスト6件失敗
- `tests/app/test_whisper_batch.py::TestPickNextJob::test_pick_next_job_success`
- `tests/app/test_whisper_batch.py::TestPickNextJob::test_pick_next_job_launched_status`  
- `tests/app/test_whisper_batch.py::TestProcessJob::test_process_job_success_single_speaker`
- `tests/app/test_whisper_batch.py::TestWhisperBatchUtilities::test_data_validation`
- `tests/app/test_whisper_integration.py::TestWhisperIntegrationWorkflow::test_whisper_workflow_with_mocks`
- `tests/app/test_whisper_integration.py::TestWhisperAPIIntegration::test_whisper_job_creation`

**エラー詳細**:
```python
# tests/app/test_whisper_batch.py:972
assert validated_data.job_id == "test-validation"
# → AttributeError: 'WhisperJobData' object has no attribute 'job_id'

# whisper_batch/app/main.py:132  
job_id = job_data.job_id
# → AttributeError: 'WhisperJobData' object has no attribute 'job_id'
```

**根本原因**: Pydantic v2でのフィールドアクセス方法の変更
- `common_utils/class_types.py:92` で `jobId: str = Field(alias="job_id")` と定義
- アクセス時は `job_data.jobId` または `job_data.model_dump()['job_id']` を使用する必要

### 2. WhisperUploadRequest フィールドアクセス問題

**症状**:
```
AttributeError: 'WhisperUploadRequest' object has no attribute 'gcs_object'
```

**発生箇所**: `backend/app/api/whisper.py:112`
```python
if not whisper_request.gcs_object:
    # → AttributeError: 'WhisperUploadRequest' object has no attribute 'gcs_object'
```

**根本原因**: `common_utils/class_types.py:70` で `gcsObject: Optional[str] = Field(default=None, alias="gcs_object")` と定義されているため、アクセス時は `whisper_request.gcsObject` を使用する必要

### 3. モック設定不備

**症状**:
```
AssertionError: Expected 'transcribe_audio' to have been called once. Called 0 times.
```

**発生箇所**:
- `tests/app/test_whisper_batch.py::TestProcessJob::test_process_job_success_single_speaker`
- `tests/app/test_whisper_integration.py::TestWhisperIntegrationWorkflow::test_whisper_workflow_with_mocks`

**原因**: create_autospec + side_effect パターンが未実装のため、モックが適切に呼び出されていない

## ⚠️ 中優先度問題

### 4. エミュレータテストのスキップ
- **GCS依存テスト**: 4テストがスキップ（Docker利用可能だが条件判定で除外）
- **Firestore依存テスト**: 2テストがスキップ（gcloud依存関係）

### 5. 廃止予定警告
```
DeprecationWarning: 'audioop' is deprecated and slated for removal in Python 3.13
RuntimeWarning: Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work
```

# Build and development instructions

## 基本テスト実行コマンド

### 全体テスト（推奨）
```bash
# エミュレータ起動
python tests/app/gcp_emulator_run.py --init-data &

# 環境変数設定 + 全テスト実行
FIRESTORE_EMULATOR_HOST=localhost:8081 \
STORAGE_EMULATOR_HOST=http://localhost:9000 \
GCS_EMULATOR_HOST=http://localhost:9000 \
GOOGLE_CLOUD_PROJECT=supportaisystem20250412 \
DEBUG=1 \
ENVIRONMENT=test \
FRONTEND_PATH=/tmp/frontend \
pytest tests/app/ -vv --tb=short -s
```

### 動作確認済みテスト（安全実行）
```bash
# 基本テスト + エミュレータテスト
FIRESTORE_EMULATOR_HOST=localhost:8081 \
STORAGE_EMULATOR_HOST=http://localhost:9000 \
GCS_EMULATOR_HOST=http://localhost:9000 \
GOOGLE_CLOUD_PROJECT=supportaisystem20250412 \
DEBUG=1 \
ENVIRONMENT=test \
FRONTEND_PATH=/tmp/frontend \
pytest tests/app/test_simple.py tests/app/test_emulator_availability.py -vv --tb=short
```

### 問題テストの除外実行
```bash
# Whisper関連テストを除外
FIRESTORE_EMULATOR_HOST=localhost:8081 \
STORAGE_EMULATOR_HOST=http://localhost:9000 \
GCS_EMULATOR_HOST=http://localhost:9000 \
GOOGLE_CLOUD_PROJECT=supportaisystem20250412 \
DEBUG=1 \
ENVIRONMENT=test \
FRONTEND_PATH=/tmp/frontend \
pytest tests/app/ -k "not (whisper_batch or whisper_combine or whisper_diarize or whisper_integration or whisper_transcribe or test_improvements or test_whisper_api or test_whisper_api_enhanced)" -vv --tb=short
```

## デバッグ・解析コマンド

### テスト失敗時のデバッグ
```bash
# デバッガ起動
pytest tests/app/test_whisper_batch.py::TestWhisperBatchUtilities::test_data_validation --pdb

# 特定テストの詳細出力
pytest tests/app/test_whisper_batch.py::TestPickNextJob::test_pick_next_job_success -vv -s --tb=long
```

### パフォーマンス分析
```bash
# 実行時間測定
pytest tests/app/ --durations=10

# カバレッジ測定（修正後）
pytest tests/app/ --cov=backend/app --cov-report=html
```

## エミュレータ管理

### エミュレータ起動確認
```bash
# プロセス確認
ps aux | grep -E "(gcp_emulator_run|firestore|fake-gcs)" | grep -v grep

# ポート使用状況確認  
netstat -tulpn | grep -E "(8081|9000)"
```

### エミュレータ停止・再起動
```bash
# エミュレータ停止
pkill -f gcp_emulator_run.py
docker stop $(docker ps -q --filter "name=fake-gcs")

# 再起動
python tests/app/gcp_emulator_run.py --init-data &
```

# Relevant file paths

## テスト関連ファイル
- `tests/app/test_simple.py` - 基本機能テスト（100%成功）
- `tests/app/test_emulator_availability.py` - エミュレータ可用性テスト
- `tests/app/test_whisper_batch.py` - Whisperバッチ処理テスト（問題あり）
- `tests/app/test_whisper_integration.py` - Whisper統合テスト（問題あり）
- `tests/app/test_whisper_emulator_example.py` - Whisperエミュレータ例
- `tests/app/gcp_emulator_run.py` - エミュレータ起動スクリプト
- `tests/requirements.txt` - テスト用依存関係

## データモデル関連ファイル（要修正）
- `common_utils/class_types.py:89-125` - WhisperJobData定義（Pydantic v2対応要）
- `common_utils/class_types.py:68-86` - WhisperUploadRequest定義（フィールドアクセス要修正）

## API関連ファイル（要修正）
- `backend/app/api/whisper.py:58` - VALID_STATUSES定義（修正済み）
- `backend/app/api/whisper.py:112` - gcs_objectアクセス（要修正）
- `backend/app/api/geocoding.py:11,31` - GeocodingRequest使用（修正済み）

## バッチ処理関連ファイル（要修正）
- `whisper_batch/app/main.py:132` - job_idアクセス（要修正）
- `whisper_batch/app/main.py:304,306` - ログ出力部分

## テスト設定ファイル
- `pytest.ini` - pytest設定
- `backend/pytest.ini` - バックエンド専用pytest設定

## 環境・設定ファイル
- `backend/app/main.py:100` - 静的ファイルパス設定
- `frontend/src/assets/` - フロントエンド静的ファイル
- `/tmp/frontend/assets/` - テスト用静的ファイル配置先