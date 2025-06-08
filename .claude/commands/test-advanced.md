アドバンスドなテスト技術とベストプラクティスを実装してください：

## 振る舞い駆動設計とテスト戦略

### 処理フローロジックと中核ロジックの分離
```python
# ❌ 悪い例：処理フローと中核ロジックが混在
class AudioProcessingService:
    def process_audio_request(self, audio_data, config):
        # ファイル保存
        file_path = self.save_to_temp_file(audio_data)
        
        # 音声処理
        if config.noise_reduction:
            audio_data = self.apply_noise_reduction(audio_data)
        if config.volume_normalize:
            audio_data = self.normalize_volume(audio_data)
            
        # 結果保存
        result_path = self.save_processed_audio(audio_data)
        
        # 通知送信
        self.send_notification(config.user_id, result_path)
        
        return result_path

# ✅ 良い例：関心の分離
class AudioProcessingService:
    """アプリケーションサービス：処理フローに専念"""
    def __init__(self, processor: AudioProcessor, storage: AudioStorage):
        self.processor = processor
        self.storage = storage
    
    def process_audio_request(self, audio_data, config):
        # 1. 音声処理（中核ロジック）
        processed_audio = self.processor.process_audio(audio_data, config)
        
        # 2. 保存（インフラ）
        result_path = self.storage.save_audio(processed_audio)
        
        # 3. 最終料金決定（中核ロジック）
        return result_path

class AudioProcessor:
    """中核ロジック：音声処理の振る舞いに専念"""
    def process_audio(self, audio_data: AudioData, config: ProcessingConfig) -> AudioData:
        if config.noise_reduction:
            audio_data = self._apply_noise_reduction(audio_data)
        if config.volume_normalize:
            audio_data = self._normalize_volume(audio_data)
        return audio_data
```

### 大きな振る舞いのテスト戦略
```python
# 中核ロジックのテスト：網羅的にテスト
class TestAudioProcessor:
    """音声処理の振る舞いを網羅的にテスト"""
    
    @pytest.mark.parametrize(
        ["noise_reduction", "volume_normalize", "expected_operations"],
        [
            (True, True, ["noise_reduction", "volume_normalize"]),
            (True, False, ["noise_reduction"]),
            (False, True, ["volume_normalize"]),
            (False, False, []),
        ]
    )
    def test_process_audio_設定に応じた処理が実行されること(
        self, noise_reduction, volume_normalize, expected_operations
    ):
        # 詳細なテスト実装
        pass

# アプリケーションサービスのテスト：代表的なパターンのみ
class TestAudioProcessingService:
    """処理フロー統合テスト：代表例＋エッジケースのみ"""
    
    def test_process_audio_request_正常な処理フロー(self):
        """代表的な正常パターン"""
        pass
    
    def test_process_audio_request_音声処理でエラー発生時(self):
        """エラーハンドリングのエッジケース"""
        pass
```

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

## 2. テストダブル戦略：スタブとモックの適切な使い分け

### テストダブル利用指針の実践

#### 1. まず、テストダブルなしでテスト
```python
def test_audio_validator_有効なWAVファイルでTrue返却():
    """純粋なロジックはテストダブル不要"""
    validator = AudioValidator()
    result = validator.is_valid_audio_file("sample.wav", file_size=1024*1024)
    assert result is True

def test_price_calculator_大人通常料金で2000円():
    """ビジネスロジックのコア部分"""
    calculator = PriceCalculator()
    result = calculator.calculate_base_price(CustomerType.ADULT, MovieType.REGULAR)
    assert result == 2000
```

#### 2. スタブ：間接入力の制御に使用
```python
def test_weather_service_API障害時デフォルト値返却():
    """外部API障害をスタブで再現"""
    with patch('weather_api.get_current_weather') as stub_weather:
        stub_weather.side_effect = ConnectionError("API接続失敗")
        
        service = WeatherService()
        result = service.get_weather_info("Tokyo")
        
        # デフォルト値の検証
        assert result.temperature == 20  # デフォルト値
        assert result.status == "UNKNOWN"

def test_file_processor_読み込みエラー時の処理():
    """制御困難なファイルI/Oエラーを再現"""
    with patch('builtins.open', side_effect=IOError("Permission denied")):
        processor = FileProcessor()
        result = processor.process_file("protected_file.txt")
        
        assert result.success is False
        assert "Permission denied" in result.error_message
```

#### 3. モック：間接出力の観測（慎重に使用）
```python
def test_notification_service_重要通知でメール送信実行():
    """
    モック使用の事前検討済み事項：
    - メール送信は外部との契約として観察可能な振る舞い
    - 副作用をなくす設計変更は困難（通知が主目的）
    - 実際のメール送信は統合テストで確認
    """
    with patch('email_service.send_email') as mock_email:
        notification = NotificationService()
        notification.notify_critical_alert("システム障害発生")
        
        # 外部システムとの契約を検証
        mock_email.assert_called_once_with(
            to="admin@company.com",
            subject="【緊急】システム障害発生",
            body="システム障害発生",
            priority="HIGH"
        )

def test_audit_logger_機密操作でログ出力実行():
    """監査ログの出力確認（コンプライアンス要件）"""
    with patch('audit_logger.log_security_event') as mock_audit:
        service = SecurityService()
        service.access_sensitive_data(user_id="user123", data_type="personal_info")
        
        mock_audit.assert_called_once_with(
            event_type="SENSITIVE_DATA_ACCESS",
            user_id="user123", 
            resource="personal_info",
            timestamp=ANY
        )
```

### autospecを使った安全なモック（必要時のみ）
```python
from unittest.mock import create_autospec, patch

def test_gcs_upload_安全なモック設計():
    """create_autospec + side_effectパターン"""
    # 実際のクラスからautospecを作成
    mock_client_class = create_autospec(storage.Client, spec_set=True)
    
    # カスタム振る舞いを定義
    def upload_behavior(bucket_name, blob_name, file_path):
        if not file_path.endswith('.wav'):
            raise ValueError("Invalid file format")
        return f"gs://{bucket_name}/{blob_name}"
    
    # autospecモックにカスタム振る舞いを注入
    mock_instance = mock_client_class.return_value
    mock_instance.upload_blob.side_effect = upload_behavior
    
    with patch('google.cloud.storage.Client', return_value=mock_instance):
        uploader = FileUploader()
        
        # ✅ 正常ケース
        result = uploader.upload_audio("bucket", "test.wav", "sample.wav")
        assert result.startswith("gs://")
        
        # ✅ エラーケース（カスタム振る舞いによる検証）
        with pytest.raises(ValueError, match="Invalid file format"):
            uploader.upload_audio("bucket", "test.txt", "invalid.txt")
```

### 複数レイヤーのテストダブル使用（統合テスト）
```python
def test_whisper_processing_pipeline_統合テスト():
    """
    注意：統合テストでのみ複数モック使用
    各コンポーネントの単体テストは個別に実施済み
    """
    with patch('gcp_storage.upload_blob') as stub_storage, \
         patch('pub_sub.publish_message') as stub_pubsub, \
         patch('firestore.save_document') as stub_firestore:
        
        # スタブの設定（間接入力制御）
        stub_storage.return_value = "gs://bucket/audio.wav"
        stub_pubsub.return_value.result.return_value = "msg-123"
        stub_firestore.return_value = None
        
        # 統合処理の実行
        result = whisper_pipeline.process_audio_request(
            audio_data=b"fake_audio_data",
            user_id="user123"
        )
        
        # 統合結果の検証（各ステップの実行確認）
        assert result["status"] == "processing"
        assert result["job_id"] is not None
        
        # 各外部サービス呼び出しの確認
        stub_storage.assert_called_once()
        stub_pubsub.assert_called_once()
        stub_firestore.assert_called_once()
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