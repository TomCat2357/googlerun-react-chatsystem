テスト環境のセットアップと設定を行ってください：

## 1. 基本環境セットアップ

### 仮想環境のアクティベート
```bash
# プロジェクトルートで実行
source .venv/bin/activate
```

### テスト依存関係のインストール
```bash
# uvを使った高速インストール
/root/.local/bin/uv pip install -r tests/requirements.txt

# 追加パッケージが必要な場合
/root/.local/bin/uv pip install pytest-mock pytest-clarity pytest-randomly pytest-freezegun
```

## 2. pytest設定ファイル作成・更新

### pytest.ini設定
```ini
[pytest]
addopts = -vv --tb=short -s
pythonpath = ["backend", "common_utils"]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
disable_test_id_escaping_and_forfeit_all_rights_to_community_support = true
markers =
    slow: 時間のかかるテスト
    integration: 統合テスト
    unit: 単体テスト
    api: APIテスト
    whisper: Whisper関連テスト
    chat: チャット機能テスト
    auth: 認証関連テスト
```

### conftest.py設定例
```python
import pytest
import os
from unittest.mock import Mock

@pytest.fixture(scope="session")
def test_config():
    """テスト用設定"""
    os.environ["DEBUG"] = "1"
    os.environ["ENVIRONMENT"] = "test"
    return {"debug": True, "environment": "test"}

@pytest.fixture(scope="function")
def mock_firebase():
    """Firebase mock"""
    with pytest.mock.patch("firebase_admin.auth") as mock_auth:
        yield mock_auth

@pytest.fixture(scope="function")
def mock_gcp_client():
    """GCP クライアント mock"""
    mock_client = Mock()
    mock_client.upload_blob.return_value = "gs://bucket/file.wav"
    return mock_client

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """テスト環境の自動セットアップ"""
    # ログレベル設定
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    # テスト用一時ディレクトリ
    os.makedirs("/tmp/test_audio", exist_ok=True)
    
    yield
    
    # クリーンアップ
    import shutil
    if os.path.exists("/tmp/test_audio"):
        shutil.rmtree("/tmp/test_audio")
```

## 3. GCP エミュレータ設定

### エミュレータ起動
```bash
# バックグラウンドで起動
python tests/app/gcp_emulator_run.py &

# 起動確認
ps aux | grep gcp_emulator
```

### 環境変数設定
```bash
# エミュレータ用環境変数
export FIRESTORE_EMULATOR_HOST=localhost:8080
export PUBSUB_EMULATOR_HOST=localhost:8085
export STORAGE_EMULATOR_HOST=http://localhost:9199
```

## 4. テストデータ準備

### サンプル音声ファイル
```bash
# テスト用音声ディレクトリ作成
mkdir -p tests/data/audio

# サンプルファイル配置（実際のプロジェクトに応じて）
# tests/data/audio/sample.wav
# tests/data/audio/sample.mp3
```

### モックデータ設定
```python
# tests/data/mock_responses.py
MOCK_WHISPER_RESPONSE = {
    "transcription": "これはテスト音声です",
    "confidence": 0.95,
    "language": "ja"
}

MOCK_CHAT_RESPONSE = {
    "message": "テスト応答です",
    "model": "gemini-pro",
    "timestamp": "2024-01-01T00:00:00Z"
}
```

## 5. IDE・エディタ設定

### VS Code設定 (.vscode/settings.json)
```json
{
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
        "tests",
        "-vv",
        "--tb=short"
    ],
    "python.testing.autoTestDiscoverOnSaveEnabled": true
}
```

### PyCharm設定
1. File → Settings → Tools → Python Integrated Tools
2. Default test runner: pytest
3. Additional arguments: `-vv --tb=short -s`

## 6. CI/CD用設定

### GitHub Actions設定例
```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -r tests/requirements.txt
      - name: Run tests
        run: pytest --junitxml=test-results.xml --cov=backend
```

## 7. トラブルシューティング

### よくある問題と解決策

**ImportError**:
```bash
# PYTHONPATH設定
export PYTHONPATH="${PYTHONPATH}:$(pwd)/backend:$(pwd)/common_utils"
```

**モジュール見つからない**:
```bash
# 開発モードでインストール
pip install -e .
```

**権限エラー**:
```bash
# 実行権限付与
chmod +x tests/app/gcp_emulator_run.py
```

**ポート競合**:
```bash
# プロセス確認・終了
lsof -i :8080
kill -9 <PID>
```