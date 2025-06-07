アドバンスドなテスト技術とベストプラクティスを実装してください：

## 1. 高度なpytestテクニック

### パラメータ化テスト（parametrize）
```python
import pytest

@pytest.mark.parametrize(
    ["audio_format", "expected_duration", "expected_channels"],
    [
        ("wav", 5.0, 1),
        ("mp3", 5.2, 2), 
        ("m4a", 4.8, 1),
    ],
    ids=[
        "WAV形式_モノラル5秒",
        "MP3形式_ステレオ5秒",
        "M4A形式_モノラル5秒",
    ],
)
def test_audio_processing_各形式で正しく処理されること(audio_format, expected_duration, expected_channels):
    file_path = f"tests/data/sample.{audio_format}"
    result = process_audio_file(file_path)
    
    assert result.duration == pytest.approx(expected_duration, rel=0.1)
    assert result.channels == expected_channels
```

### フィクスチャの活用
```python
@pytest.fixture(scope="session")
def audio_processor():
    """音声処理器のセッションスコープフィクスチャ"""
    processor = AudioProcessor()
    processor.initialize()
    yield processor
    processor.cleanup()

@pytest.fixture(scope="function")
def temp_audio_file():
    """一時音声ファイルの関数スコープフィクスチャ"""
    import tempfile
    import os
    
    # 一時ファイル作成
    fd, path = tempfile.mkstemp(suffix='.wav')
    os.close(fd)
    
    # テスト用音声データ作成（実際の実装に応じて）
    create_test_audio(path)
    
    yield path
    
    # クリーンアップ
    if os.path.exists(path):
        os.remove(path)
```

### カスタムマーカーの活用
```python
# テストファイル内
@pytest.mark.slow
@pytest.mark.integration
def test_whisper_batch_full_pipeline_完全な処理パイプラインが正常動作すること():
    """時間のかかる統合テスト"""
    pass

@pytest.mark.unit
def test_audio_validator_無効なファイル形式でFalseを返すこと():
    """高速な単体テスト"""
    pass

# 実行例
# pytest -m "unit"                    # 単体テストのみ
# pytest -m "not slow"                # 遅いテスト以外
# pytest -m "integration and whisper" # 統合テスト かつ Whisper関連
```

### フィクスチャの条件付き動作
```python
@pytest.fixture
def database_client(request):
    """マーカーに応じてDB設定を変更"""
    if request.node.get_closest_marker("use_real_db"):
        client = RealDatabaseClient()
    else:
        client = MockDatabaseClient()
    
    yield client
    client.close()

@pytest.mark.use_real_db
def test_data_persistence_実際のDBで永続化確認():
    pass
```

## 2. モック戦略とベストプラクティス

### autospecを使った安全なモック
```python
from unittest.mock import patch, Mock

@patch('backend.app.api.speech.VertexAI', autospec=True)
def test_speech_api_vertex_ai_呼び出し引数が正しいこと(mock_vertex):
    """autospecで引数チェックを強化"""
    mock_instance = Mock()
    mock_vertex.return_value = mock_instance
    
    # テスト実行
    result = call_vertex_ai_speech("test.wav")
    
    # 引数チェック（autospecにより型チェックも実行される）
    mock_vertex.assert_called_once_with(
        project="test-project",
        location="us-central1"
    )
```

### コンテキストマネージャーとしてのモック
```python
def test_file_upload_with_cleanup():
    with patch('backend.app.utils.gcp_storage.upload_blob') as mock_upload:
        mock_upload.return_value = "gs://bucket/file.wav"
        
        # テスト実行
        result = upload_audio_file("test.wav")
        
        # 検証
        assert result.startswith("gs://")
        mock_upload.assert_called_once()
```

### 複数レイヤーのモック
```python
@patch('backend.app.api.whisper.pub_sub_client')
@patch('backend.app.api.whisper.storage_client')
@patch('backend.app.api.whisper.firestore_client')
def test_whisper_api_integration_全依存関係をモック(
    mock_firestore, mock_storage, mock_pubsub
):
    # 各モックの設定
    mock_storage.upload_blob.return_value = "gs://bucket/audio.wav"
    mock_pubsub.publish.return_value.result.return_value = "message-id"
    mock_firestore.collection.return_value.document.return_value.set.return_value = None
    
    # テスト実行と検証
    result = process_whisper_request("audio_data")
    assert result["status"] == "processing"
```

## 3. テストデータ管理

### Fakerライブラリの活用
```python
from faker import Faker
import pytest

@pytest.fixture
def fake_user_data():
    fake = Faker('ja_JP')  # 日本語ロケール
    return {
        "name": fake.name(),
        "email": fake.email(),
        "address": fake.address(),
        "phone": fake.phone_number()
    }

def test_user_registration_正常なデータで成功すること(fake_user_data):
    result = register_user(fake_user_data)
    assert result.success is True
```

### テストデータファクトリ
```python
# tests/factories.py
class AudioFileFactory:
    @staticmethod
    def create_wav(duration=5.0, sample_rate=16000):
        """WAVファイルのテストデータ作成"""
        import numpy as np
        import wave
        
        samples = int(duration * sample_rate)
        data = np.random.uniform(-1, 1, samples)
        
        return (data * 32767).astype(np.int16)
    
    @staticmethod
    def create_test_file(format="wav", **kwargs):
        """各種形式のテストファイル作成"""
        if format == "wav":
            return AudioFileFactory.create_wav(**kwargs)
        # 他の形式も同様に実装
```

## 4. 時間とランダム性のテスト

### freezegunを使った時間固定
```python
from freezegun import freeze_time
import pytest

@freeze_time("2024-01-01 12:00:00")
def test_timestamp_generation_固定時刻でのタイムスタンプ():
    result = generate_timestamp()
    assert result == "2024-01-01T12:00:00Z"

@pytest.mark.parametrize("test_time", [
    "2024-01-01 09:00:00",  # 営業時間内
    "2024-01-01 18:00:00",  # 営業時間外
])
def test_business_hours_check(test_time):
    with freeze_time(test_time):
        result = is_business_hours()
        expected = "09:00" <= test_time.split()[1] <= "17:00"
        assert result == expected
```

### ランダム性のテスト
```python
def test_random_generation_一意性確認():
    """ランダム生成の一意性をテスト"""
    results = set()
    for _ in range(100):
        result = generate_random_id()
        assert result not in results
        results.add(result)
```

## 5. デバッグとトラブルシューティング

### 高度なデバッグ技術
```python
def test_complex_processing_with_debug():
    # ブレークポイントでの変数確認
    input_data = prepare_test_data()
    breakpoint()  # pdb起動
    
    # 中間結果の確認
    intermediate = process_step_1(input_data)
    print(f"Step 1 result: {intermediate}")  # -s オプションで表示
    
    final_result = process_step_2(intermediate)
    assert final_result.is_valid()

# ipdbを使った高機能デバッグ
# pytest --pdbcls=IPython.terminal.debugger:Pdb
```

### エラー情報の詳細化
```python
def test_with_detailed_error_info():
    """詳細なエラー情報付きテスト"""
    try:
        result = complex_operation()
        assert result.status == "success", f"Operation failed: {result.error_details}"
    except Exception as e:
        pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")
```

### ログ出力のテスト
```python
import logging

def test_logging_output(caplog):
    """ログ出力のテスト"""
    with caplog.at_level(logging.INFO):
        perform_logged_operation()
    
    assert "処理を開始します" in caplog.text
    assert len(caplog.records) == 2
    assert caplog.records[0].levelname == "INFO"
```

## 6. パフォーマンステスト

### 実行時間の測定
```python
import time
import pytest

def test_performance_whisper_processing():
    """音声処理のパフォーマンステスト"""
    start_time = time.time()
    
    result = process_audio_file("tests/data/large_audio.wav")
    
    end_time = time.time()
    duration = end_time - start_time
    
    # 10秒以内での処理を期待
    assert duration < 10.0, f"処理時間が長すぎます: {duration:.2f}秒"
    assert result.success is True

@pytest.mark.benchmark
def test_api_response_time():
    """API応答時間のベンチマーク"""
    # pytest-benchmark プラグイン使用
    pass
```

## 7. 継続的インテグレーション対応

### 環境別テスト実行
```python
import os
import pytest

@pytest.mark.skipif(
    os.environ.get("CI") != "true",
    reason="CI環境でのみ実行"
)
def test_ci_specific_functionality():
    pass

@pytest.mark.skipif(
    not os.environ.get("INTEGRATION_TEST"),
    reason="統合テスト環境が設定されていません"
)
def test_external_api_integration():
    pass
```

### テスト結果の出力形式
```bash
# JUnit XML (CI/CD用)
pytest --junitxml=test-results.xml

# HTMLレポート
pytest --html=report.html --self-contained-html

# カバレッジレポート
pytest --cov=backend --cov-report=html --cov-report=xml
```