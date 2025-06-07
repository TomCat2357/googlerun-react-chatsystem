# Whisperテストスイート

このディレクトリには、Whisper音声文字起こしシステムの包括的なテストが含まれています。

## テストファイルの構成

### 核となるテストファイル

- **`conftest.py`** - 共通のテスト設定とフィクスチャ
- **`test_whisper_api.py`** - Whisper API エンドポイントのテスト
- **`test_whisper_batch.py`** - バッチ処理のテスト  
- **`test_whisper_transcribe.py`** - 文字起こし機能のテスト
- **`test_whisper_diarize.py`** - 話者分離機能のテスト
- **`test_whisper_combine.py`** - 結果統合機能のテスト
- **`test_whisper_integration.py`** - 統合テスト

### サポートファイル

- **`gcp_emulator_run.py`** - GCPエミュレータ起動スクリプト
- **`test_emulator_availability.py`** - エミュレータ利用可能性テスト
- **`test_whisper_emulator_example.py`** - エミュレータ使用例（通常はスキップ）
- **`requirements.txt`** - テスト依存関係

## 前提条件

### 必要なソフトウェア

1. **Python 3.8+**
2. **Docker** - GCSエミュレータ用
3. **Google Cloud SDK** - Firestoreエミュレータ用

### 依存関係のインストール

```bash
# テスト用の依存関係をインストール
pip install -r tests/requirements.txt

# プロジェクトの依存関係もインストール（必要に応じて）
pip install -r backend/requirements.txt
pip install -r whisper_batch/requirements.txt
```

## テストの実行

### 基本的なテスト実行

```bash
# プロジェクトルートから実行
cd /path/to/googlerun-react-chatsystem

# 全てのWhisperテストを実行
pytest tests/app/ -v

# 特定のテストファイルを実行
pytest tests/app/test_whisper_api.py -v

# 特定のテストクラスを実行
pytest tests/app/test_whisper_api.py::TestWhisperUpload -v

# 特定のテスト関数を実行
pytest tests/app/test_whisper_api.py::TestWhisperUpload::test_upload_audio_success -v
```

### エミュレータを使用したテスト

統合テストを実行する前に、GCPエミュレータを起動する必要があります：

```bash
# エミュレータを起動（別ターミナルで）
python tests/app/gcp_emulator_run.py --init-data

# エミュレータが起動している状態で統合テストを実行
pytest tests/app/test_whisper_integration.py -v -m integration
```

### テストカテゴリ別実行

```bash
# 統合テストのみ実行
pytest tests/app/ -m integration -v

# 統合テスト以外を実行
pytest tests/app/ -m "not integration" -v

# エミュレータ利用可能性テスト
pytest tests/app/test_emulator_availability.py -v

# 非同期テストのみ実行
pytest tests/app/ -k "async" -v
```

### テスト実行オプション

```bash
# カバレッジレポート付きで実行
pytest tests/app/ --cov=backend --cov=whisper_batch --cov-report=html -v

# 並列実行（高速化）
pytest tests/app/ -n auto -v

# 詳細な出力
pytest tests/app/ -v -s

# 失敗時に即座に停止
pytest tests/app/ -x -v

# 警告を表示
pytest tests/app/ -v --disable-warnings
```

## テスト環境の設定

### 環境変数

テストは以下の環境変数を使用します：

```bash
# テスト用のプロジェクト設定
export GCP_PROJECT_ID="test-whisper-project"
export GCS_BUCKET_NAME="test-whisper-bucket" 
export FIRESTORE_EMULATOR_HOST="localhost:8081"
export STORAGE_EMULATOR_HOST="http://localhost:9000"

# Whisper関連設定
export WHISPER_JOBS_COLLECTION="whisper_jobs"
export WHISPER_MAX_SECONDS="1800"
export WHISPER_MAX_BYTES="104857600"
export HF_AUTH_TOKEN="your-huggingface-token"  # 話者分離テスト用
```

### Docker設定

GCSエミュレータはDockerを使用します：

```bash
# Dockerが実行中であることを確認
docker --version
docker ps

# 必要に応じてDockerイメージを事前にプル
docker pull fsouza/fake-gcs-server:latest
```

## トラブルシューティング

### よくある問題と解決方法

#### 1. エミュレータ起動の問題

```bash
# ポートが使用中の場合
lsof -i :8081  # Firestoreエミュレータのポート
lsof -i :9000  # GCSエミュレータのポート

# プロセスを終了
kill -9 <PID>
```

#### 2. Docker関連の問題

```bash
# Dockerデーモンが停止している場合
sudo systemctl start docker

# 権限の問題
sudo usermod -aG docker $USER
# ログアウト/ログインが必要
```

#### 3. 依存関係の問題

```bash
# 仮想環境を使用することを推奨
python -m venv venv
source venv/bin/activate  # Linux/Mac
# または
venv\Scripts\activate  # Windows

# 依存関係を再インストール
pip install --upgrade pip
pip install -r tests/requirements.txt --force-reinstall
```

#### 4. テスト実行時のエラー

```bash
# モジュールが見つからない場合
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 権限の問題
chmod +x tests/app/gcp_emulator_run.py

# 一時ディレクトリの問題
export TMPDIR=/tmp
```

## テストデータとモック

### テスト用音声ファイル

テストでは以下の方法で音声ファイルを生成しています：

- **`sample_audio_file`フィクスチャ**: 1秒間の440Hzサイン波
- **PyDub**: 音声データの生成と操作
- **NumPy**: 波形データの生成

### モック対象

- **Whisperモデル**: 実際のAI処理をモック
- **HuggingFace API**: 話者分離処理をモック  
- **GCPサービス**: エミュレータまたはモックを使用
- **外部APIコール**: すべてモック化

## CI/CD統合

### GitHub Actions設定例

```yaml
name: Whisper Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      docker:
        image: docker:20.10-git
        
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
        
    - name: Install dependencies
      run: |
        pip install -r tests/requirements.txt
        
    - name: Install Google Cloud SDK
      uses: google-github-actions/setup-gcloud@v1
      
    - name: Run unit tests
      run: |
        pytest tests/app/ -m "not integration" --cov=backend --cov=whisper_batch
        
    - name: Run integration tests
      run: |
        python tests/app/gcp_emulator_run.py --init-data &
        sleep 10
        pytest tests/app/ -m integration
```

## パフォーマンステスト

### 大容量ファイルのテスト

```bash
# メモリ使用量を監視しながら実行
pytest tests/app/test_whisper_integration.py::TestWhisperPerformanceIntegration -v -s
```

### 負荷テスト

```bash
# 並行処理のテスト
pytest tests/app/test_whisper_integration.py::TestWhisperIntegration::test_whisper_concurrent_jobs_integration -v
```

## 追加情報

### テストカバレッジ

```bash
# カバレッジレポートの生成
pytest tests/app/ --cov=backend --cov=whisper_batch --cov-report=html --cov-report=term

# HTMLレポートを確認
open htmlcov/index.html
```

### ログとデバッグ

```bash
# ログレベルを上げてテスト実行
export LOG_LEVEL=DEBUG
pytest tests/app/ -v -s --log-cli-level=DEBUG
```

### テストデータのクリーンアップ

```bash
# 一時ファイルとエミュレータデータのクリーンアップ
# エミュレータはin-memoryなので停止時に自動削除されます
docker container prune -f
docker image prune -f
```

## 貢献について

新しいテストを追加する場合は、以下のガイドラインに従ってください：

1. **適切なファイルに配置** - 機能別にテストファイルを分ける
2. **フィクスチャの活用** - `conftest.py`の共通フィクスチャを使用
3. **適切なモック** - 外部依存を適切にモック
4. **テストの独立性** - テスト間で状態を共有しない
5. **わかりやすい名前** - テスト名から何をテストしているかを明確に
6. **適切なマーカー** - `@pytest.mark.integration`等を使用

## 参考資料

- [pytest公式ドキュメント](https://docs.pytest.org/)
- [Google Cloud Emulator](https://cloud.google.com/sdk/gcloud/reference/beta/emulators)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pandas Testing](https://pandas.pydata.org/docs/reference/general.html#testing)
