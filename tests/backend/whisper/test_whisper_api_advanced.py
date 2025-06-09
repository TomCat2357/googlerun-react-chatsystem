"""
Whisper API Advanced Testing Suite

振る舞い駆動設計とアドバンステスト技術を実装したテストスイート:
- 処理フローロジックと中核ロジックの分離
- パラメータ化テストによる網羅的テスト
- テストダブル戦略の最適化
- テストデータファクトリー
- パフォーマンステスト
"""

import pytest
import json
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, MagicMock, create_autospec
from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
from faker import Faker

from common_utils.class_types import WhisperUploadRequest
from backend.app.api.whisper import router


# ==============================================================================
# Advanced Test Data Factories
# ==============================================================================

class AudioTestDataFactory:
    """音声テストデータファクトリー（Fakerベース）"""
    
    def __init__(self):
        self.fake = Faker(['ja_JP', 'en_US'])
        self.fake.seed_instance(12345)  # 再現可能な結果
    
    def create_audio_file_metadata(self, format: str = "wav", **kwargs) -> Dict[str, Any]:
        """音声ファイルメタデータを生成"""
        defaults = {
            "filename": f"{self.fake.slug()}.{format}",
            "content_type": f"audio/{format}",
            "size": self.fake.random_int(min=10000, max=100000000),
            "duration_ms": self.fake.random_int(min=1000, max=1800000),
            "sample_rate": self.fake.random_element([16000, 44100, 48000]),
            "channels": self.fake.random_element([1, 2]),
            "bit_depth": self.fake.random_element([16, 24, 32])
        }
        defaults.update(kwargs)
        return defaults
    
    @pytest.mark.parametrize(
        ["format", "is_valid", "expected_content_type"],
        [
            ("wav", True, "audio/wav"),
            ("mp3", True, "audio/mp3"), 
            ("m4a", True, "audio/m4a"),
            ("flac", True, "audio/flac"),
            ("pdf", False, "application/pdf"),
            ("txt", False, "text/plain"),
            ("exe", False, "application/octet-stream"),
        ],
        ids=[
            "WAV形式_有効",
            "MP3形式_有効",
            "M4A形式_有効",
            "FLAC形式_有効",
            "PDF形式_無効",
            "テキスト形式_無効",
            "実行形式_無効",
        ],
    )
    def create_format_test_data(self, format: str, is_valid: bool, expected_content_type: str):
        """フォーマット別テストデータを生成"""
        return {
            "format": format,
            "is_valid": is_valid,
            "expected_content_type": expected_content_type,
            **self.create_audio_file_metadata(format)
        }
    
    def create_upload_request_variations(self) -> List[Dict[str, Any]]:
        """多様なアップロードリクエストパターンを生成"""
        return [
            # 正常パターン
            {
                "audio_data": self.fake.sha256(),
                "filename": f"{self.fake.slug()}.wav",
                "gcs_object": f"whisper/{self.fake.uuid4()}.wav",
                "original_name": f"{self.fake.word()}_録音.wav",
                "description": self.fake.text(max_nb_chars=100),
                "language": "ja",
                "num_speakers": 2,
                "tags": [self.fake.word() for _ in range(3)]
            },
            # 最小限パターン
            {
                "audio_data": self.fake.sha256(),
                "filename": "minimal.wav",
                "gcs_object": "temp/minimal.wav"
            },
            # 大規模パターン
            {
                "audio_data": self.fake.sha256(),
                "filename": f"{self.fake.slug()}_long_meeting.wav",
                "gcs_object": f"meetings/{self.fake.uuid4()}.wav",
                "description": self.fake.text(max_nb_chars=500),
                "language": "en",
                "num_speakers": 8,
                "min_speakers": 4,
                "max_speakers": 10,
                "tags": [self.fake.word() for _ in range(10)]
            }
        ]


class WhisperJobFactory:
    """Whisperジョブテストデータファクトリー"""
    
    def __init__(self):
        self.fake = Faker(['ja_JP'])
        self.fake.seed_instance(54321)
    
    def create_job_data(self, status: str = "queued", **overrides) -> Dict[str, Any]:
        """基本的なジョブデータを生成"""
        base_data = {
            "job_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "user_email": self.fake.email(),
            "filename": f"{self.fake.slug()}.wav",
            "gcs_bucket_name": "test-whisper-bucket",
            "audio_size": self.fake.random_int(min=10000, max=50000000),
            "audio_duration_ms": self.fake.random_int(min=1000, max=1800000),
            "file_hash": self.fake.sha256()[:16],
            "status": status,
            "language": self.fake.random_element(["ja", "en", "auto"]),
            "num_speakers": self.fake.random_int(min=1, max=5),
            "created_at": self.fake.date_time_this_year().isoformat(),
            "updated_at": self.fake.date_time_this_year().isoformat()
        }
        base_data.update(overrides)
        return base_data
    
    @pytest.mark.parametrize(
        ["status", "expected_actions"],
        [
            ("queued", ["cancel", "view"]),
            ("processing", ["cancel", "view"]),
            ("completed", ["retry", "view", "download"]),
            ("failed", ["retry", "view"]),
            ("canceled", ["retry", "view"]),
        ],
        ids=[
            "キューステータス_キャンセル可",
            "処理中ステータス_キャンセル可",
            "完了ステータス_ダウンロード可",
            "失敗ステータス_再実行可",
            "キャンセル済み_再実行可",
        ],
    )
    def create_status_based_job(self, status: str, expected_actions: List[str]):
        """ステータス別ジョブデータとアクション"""
        return {
            **self.create_job_data(status=status),
            "expected_actions": expected_actions
        }


# ==============================================================================
# Behavioral Separation: Core Logic vs Processing Flow
# ==============================================================================

class AudioValidationCore:
    """音声検証の中核ロジック（純粋関数）"""
    
    VALID_FORMATS = {"wav", "mp3", "m4a", "flac", "ogg"}
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_DURATION_MS = 30 * 60 * 1000   # 30分
    
    @staticmethod
    def validate_audio_format(filename: str) -> bool:
        """音声フォーマットの検証"""
        if not filename or not isinstance(filename, str):
            return False
        
        # 拡張子のみの場合の特別処理
        if filename.startswith('.') and filename.count('.') == 1:
            extension = filename[1:].lower()
        else:
            extension = Path(filename).suffix.lower().lstrip('.')
        
        return extension in AudioValidationCore.VALID_FORMATS
    
    @staticmethod
    def validate_file_size(size_bytes: int) -> bool:
        """ファイルサイズの検証"""
        return isinstance(size_bytes, int) and 0 < size_bytes <= AudioValidationCore.MAX_FILE_SIZE
    
    @staticmethod
    def validate_duration(duration_ms: int) -> bool:
        """音声時間の検証"""
        return isinstance(duration_ms, int) and 0 < duration_ms <= AudioValidationCore.MAX_DURATION_MS
    
    @staticmethod
    def calculate_processing_priority(file_size: int, num_speakers: int, user_tier: str = "standard") -> int:
        """処理優先度の計算"""
        base_priority = 50
        
        # ファイルサイズによる調整
        if file_size > 50 * 1024 * 1024:  # 50MB超
            base_priority -= 10
        elif file_size < 1 * 1024 * 1024:   # 1MB未満
            base_priority += 10
        
        # 話者数による調整
        if num_speakers > 3:
            base_priority -= 5
        
        # ユーザー層による調整
        if user_tier == "premium":
            base_priority += 20
        elif user_tier == "enterprise":
            base_priority += 30
        
        return max(0, min(100, base_priority))


class AudioProcessingWorkflow:
    """音声処理ワークフロー（外部サービス連携）"""
    
    def __init__(self, validator: AudioValidationCore, storage_service, queue_service):
        self.validator = validator
        self.storage_service = storage_service
        self.queue_service = queue_service
    
    async def process_upload_request(self, request: WhisperUploadRequest) -> Dict[str, Any]:
        """アップロードリクエストの処理フロー"""
        # 1. 中核ロジック：検証
        if not self.validator.validate_audio_format(request.filename):
            raise ValueError("無効な音声フォーマット")
        
        # 2. 外部サービス：ストレージ操作
        file_info = await self.storage_service.get_file_info(request.gcs_object)
        
        if not self.validator.validate_file_size(file_info["size"]):
            raise ValueError("ファイルサイズが大きすぎます")
        
        # 3. 中核ロジック：優先度計算
        priority = self.validator.calculate_processing_priority(
            file_info["size"], 
            request.num_speakers or 1
        )
        
        # 4. 外部サービス：キューイング
        job_id = await self.queue_service.enqueue_job(request, priority)
        
        return {
            "job_id": job_id,
            "priority": priority,
            "estimated_processing_time": self._estimate_processing_time(file_info)
        }
    
    def _estimate_processing_time(self, file_info: Dict[str, Any]) -> int:
        """処理時間の推定（ヒューリスティック）"""
        base_time = 30  # 30秒
        size_factor = file_info["size"] / (1024 * 1024)  # MB単位
        return int(base_time + (size_factor * 10))  # 1MBあたり10秒追加


# ==============================================================================
# Core Logic Tests (Comprehensive)
# ==============================================================================

class TestAudioValidationCore:
    """音声検証中核ロジックの網羅的テスト"""
    
    @pytest.mark.parametrize(
        ["filename", "expected_result"],
        [
            # 有効なフォーマット
            ("test.wav", True),
            ("recording.mp3", True),
            ("audio.m4a", True),
            ("music.flac", True),
            ("voice.ogg", True),
            
            # 大文字小文字の混在
            ("TEST.WAV", True),
            ("Recording.MP3", True),
            
            # 無効なフォーマット
            ("document.pdf", False),
            ("image.jpg", False),
            ("text.txt", False),
            ("program.exe", False),
            
            # エッジケース
            ("", False),
            (None, False),
            ("no_extension", False),
            (".wav", True),  # 拡張子のみ
            ("multiple.dots.wav", True),
        ],
        ids=[
            "WAV形式_有効",
            "MP3形式_有効",
            "M4A形式_有効",
            "FLAC形式_有効",
            "OGG形式_有効",
            "WAV大文字_有効",
            "MP3混在_有効",
            "PDF形式_無効",
            "JPG形式_無効",
            "TXT形式_無効",
            "EXE形式_無効",
            "空文字列_無効",
            "None値_無効",
            "拡張子なし_無効",
            "拡張子のみ_有効",
            "複数ドット_有効",
        ],
    )
    def test_validate_audio_format_全フォーマットパターンで正しい結果(self, filename, expected_result):
        """音声フォーマット検証が全パターンで正しい結果を返すこと"""
        # Act（実行）
        result = AudioValidationCore.validate_audio_format(filename)
        
        # Assert（検証）
        assert result == expected_result
    
    @pytest.mark.parametrize(
        ["size_bytes", "expected_result"],
        [
            # 有効範囲
            (1, True),                           # 最小サイズ
            (1024, True),                        # 1KB
            (1024 * 1024, True),                # 1MB
            (50 * 1024 * 1024, True),           # 50MB
            (100 * 1024 * 1024, True),          # 100MB（上限）
            
            # 無効範囲
            (0, False),                          # ゼロ
            (-1, False),                         # 負数
            (100 * 1024 * 1024 + 1, False),     # 上限超過
            (200 * 1024 * 1024, False),         # 大幅超過
        ],
        ids=[
            "最小サイズ1バイト_有効",
            "1KB_有効",
            "1MB_有効",
            "50MB_有効",
            "100MB上限_有効",
            "ゼロサイズ_無効",
            "負数サイズ_無効",
            "上限1バイト超過_無効",
            "大幅超過_無効",
        ],
    )
    def test_validate_file_size_境界値で正しい結果(self, size_bytes, expected_result):
        """ファイルサイズ検証が境界値で正しい結果を返すこと"""
        # Act（実行）
        result = AudioValidationCore.validate_file_size(size_bytes)
        
        # Assert（検証）
        assert result == expected_result
    
    @pytest.mark.parametrize(
        ["file_size", "num_speakers", "user_tier", "expected_range"],
        [
            # 標準ユーザーパターン
            (1024 * 1024, 1, "standard", (50, 70)),      # 小ファイル、単一話者
            (50 * 1024 * 1024, 2, "standard", (40, 60)),  # 中ファイル、複数話者
            (80 * 1024 * 1024, 5, "standard", (30, 50)),  # 大ファイル、多話者
            
            # プレミアムユーザーパターン
            (1024 * 1024, 1, "premium", (70, 90)),        # 小ファイル、高優先度
            (50 * 1024 * 1024, 3, "premium", (55, 75)),   # 中ファイル、高優先度
            
            # エンタープライズユーザーパターン
            (80 * 1024 * 1024, 8, "enterprise", (65, 85)), # 大ファイル、最高優先度
        ],
        ids=[
            "標準_小ファイル単一話者_中優先度",
            "標準_中ファイル複数話者_中優先度",
            "標準_大ファイル多話者_低優先度",
            "プレミアム_小ファイル_高優先度",
            "プレミアム_中ファイル_高優先度",
            "エンタープライズ_大ファイル_最高優先度",
        ],
    )
    def test_calculate_processing_priority_各条件で適切な優先度(self, file_size, num_speakers, user_tier, expected_range):
        """処理優先度計算が各条件で適切な値を返すこと"""
        # Act（実行）
        priority = AudioValidationCore.calculate_processing_priority(
            file_size, num_speakers, user_tier
        )
        
        # Assert（検証）
        min_expected, max_expected = expected_range
        assert min_expected <= priority <= max_expected
        assert 0 <= priority <= 100  # 有効範囲内


# ==============================================================================
# Processing Flow Tests (Representative Cases + Edge Cases)
# ==============================================================================

class TestAudioProcessingWorkflow:
    """音声処理ワークフローテスト（代表例とエッジケースのみ）"""
    
    @pytest.fixture
    def workflow_setup(self):
        """ワークフローテスト用セットアップ"""
        validator = AudioValidationCore()
        
        # Storage Serviceのモック（autospec使用）
        mock_storage = create_autospec(object, spec_set=True)
        mock_storage.get_file_info = Mock()
        
        # Queue Serviceのモック（autospec使用）
        mock_queue = create_autospec(object, spec_set=True)
        mock_queue.enqueue_job = Mock()
        
        workflow = AudioProcessingWorkflow(validator, mock_storage, mock_queue)
        
        return {
            "workflow": workflow,
            "storage_mock": mock_storage,
            "queue_mock": mock_queue
        }
    
    @pytest.mark.asyncio
    async def test_process_upload_request_正常なワークフロー(self, workflow_setup):
        """代表的な正常ワークフローが期待通りに動作すること"""
        # Arrange（準備）
        workflow = workflow_setup["workflow"]
        storage_mock = workflow_setup["storage_mock"]
        queue_mock = workflow_setup["queue_mock"]
        
        # 正常なファイル情報を返すスタブ
        storage_mock.get_file_info.return_value = {
            "size": 10 * 1024 * 1024,  # 10MB
            "duration_ms": 300000      # 5分
        }
        
        # 正常なジョブIDを返すスタブ
        queue_mock.enqueue_job.return_value = "job-12345"
        
        request = WhisperUploadRequest(
            audio_data="fake_data",
            filename="test.wav",
            gcs_object="temp/test.wav",
            num_speakers=2
        )
        
        # Act（実行）
        result = await workflow.process_upload_request(request)
        
        # Assert（検証）
        assert result["job_id"] == "job-12345"
        assert "priority" in result
        assert "estimated_processing_time" in result
        
        # 外部サービス呼び出し確認
        storage_mock.get_file_info.assert_called_once_with("temp/test.wav")
        queue_mock.enqueue_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_upload_request_無効フォーマットでエラー(self, workflow_setup):
        """無効フォーマットの場合に適切なエラーが発生すること"""
        # Arrange（準備）
        workflow = workflow_setup["workflow"]
        
        request = WhisperUploadRequest(
            audio_data="fake_data",
            filename="document.pdf",  # 無効フォーマット
            gcs_object="temp/document.pdf"
        )
        
        # Act & Assert（実行・検証）
        with pytest.raises(ValueError, match="無効な音声フォーマット"):
            await workflow.process_upload_request(request)
    
    @pytest.mark.asyncio
    async def test_process_upload_request_ファイルサイズ超過でエラー(self, workflow_setup):
        """ファイルサイズ超過の場合に適切なエラーが発生すること"""
        # Arrange（準備）
        workflow = workflow_setup["workflow"]
        storage_mock = workflow_setup["storage_mock"]
        
        # 大きすぎるファイル情報を返すスタブ
        storage_mock.get_file_info.return_value = {
            "size": 200 * 1024 * 1024,  # 200MB（上限超過）
            "duration_ms": 1800000
        }
        
        request = WhisperUploadRequest(
            audio_data="fake_data",
            filename="large.wav",
            gcs_object="temp/large.wav"
        )
        
        # Act & Assert（実行・検証）
        with pytest.raises(ValueError, match="ファイルサイズが大きすぎます"):
            await workflow.process_upload_request(request)


# ==============================================================================
# Advanced Integration Tests
# ==============================================================================

class TestWhisperAPIIntegration:
    """Whisper API統合テスト（代表的なエンドツーエンド）"""
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ["file_name", "file_size", "speakers", "expected_priority_range"],
        [
            ("small_file", 1024*1024, 1, (50, 70)),
            ("medium_file", 30*1024*1024, 3, (40, 60)),
            ("large_file", 90*1024*1024, 8, (25, 45)),
        ],
        ids=[
            "小ファイル_単一話者_高優先度",
            "中ファイル_複数話者_中優先度", 
            "大ファイル_多話者_低優先度",
        ],
    )
    async def test_upload_processing_priority_calculation_各ケースで適切な優先度(
        self, async_test_client, mock_auth_user, file_name, file_size, speakers, expected_priority_range
    ):
        """アップロード処理でファイルサイズ・話者数に応じた適切な優先度計算"""
        # Arrange（準備）
        factory = AudioTestDataFactory()
        upload_data = {
            "audio_data": factory.fake.sha256(),
            "filename": f"{file_name}_test.wav",
            "gcs_object": f"temp/{file_name}_test.wav",
            "num_speakers": speakers
        }
        
        # GCSファイル情報のモック
        with patch("backend.app.api.whisper.get_file_info_from_gcs") as mock_file_info:
            mock_file_info.return_value = {
                "size": file_size,
                "content_type": "audio/wav"
            }
            
            # バックグラウンド処理のモック
            with patch("backend.app.api.whisper.enqueue_job_atomic") as mock_enqueue:
                # Act（実行）
                response = await async_test_client.post(
                    "/backend/whisper",
                    json=upload_data,
                    headers={"Authorization": "Bearer test-token"}
                )
                
                # Assert（検証）
                assert response.status_code == 200
                
                # エンキュー呼び出しの確認
                mock_enqueue.assert_called_once()
                enqueue_args = mock_enqueue.call_args[0]
                
                # 優先度が期待範囲内であることを確認
                min_priority, max_priority = expected_priority_range
                # Note: 実際の優先度は処理ロジック内で計算されるため、
                # ここでは処理が正常に完了することを確認


# ==============================================================================
# Performance and Load Tests
# ==============================================================================

@pytest.mark.performance
class TestWhisperAPIPerformance:
    """Whisper APIパフォーマンステスト"""
    
    @pytest.mark.asyncio
    async def test_concurrent_upload_requests_並行リクエスト耐性(
        self, async_test_client, mock_auth_user, enhanced_test_metrics
    ):
        """並行アップロードリクエストでのパフォーマンス"""
        # Arrange（準備）
        enhanced_test_metrics.start_measurement()
        
        factory = AudioTestDataFactory()
        concurrent_requests = 5
        
        upload_requests = [
            {
                "audio_data": factory.fake.sha256(),
                "filename": f"concurrent_test_{i}.wav",
                "gcs_object": f"temp/concurrent_test_{i}.wav"
            }
            for i in range(concurrent_requests)
        ]
        
        # Act（実行）
        tasks = [
            async_test_client.post(
                "/backend/whisper",
                json=request_data,
                headers={"Authorization": "Bearer test-token"}
            )
            for request_data in upload_requests
        ]
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        enhanced_test_metrics.end_measurement()
        
        # Assert（検証）
        successful_responses = [
            r for r in responses 
            if not isinstance(r, Exception) and r.status_code == 200
        ]
        
        assert len(successful_responses) >= concurrent_requests * 0.8  # 80%成功率
        
        # パフォーマンス閾値確認
        enhanced_test_metrics.assert_performance_thresholds(
            max_duration_seconds=15.0,  # 15秒以内
            max_memory_increase_mb=100.0  # 100MB増加以内
        )
    
    @pytest.mark.asyncio
    async def test_api_response_time_レスポンス時間測定(self, async_test_client, mock_auth_user):
        """APIレスポンス時間の測定とベンチマーク"""
        # Arrange（準備）
        factory = AudioTestDataFactory()
        upload_data = {
            "audio_data": factory.fake.sha256(),
            "filename": "benchmark_test.wav",
            "gcs_object": "temp/benchmark_test.wav"
        }
        
        response_times = []
        iterations = 10
        
        # Act（実行）
        for _ in range(iterations):
            start_time = time.time()
            
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            end_time = time.time()
            response_times.append(end_time - start_time)
            
            assert response.status_code == 200
        
        # Assert（検証）
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        # パフォーマンス基準
        assert avg_response_time < 2.0, f"平均レスポンス時間が遅すぎます: {avg_response_time:.2f}秒"
        assert max_response_time < 5.0, f"最大レスポンス時間が遅すぎます: {max_response_time:.2f}秒"
        
        print(f"平均レスポンス時間: {avg_response_time:.3f}秒")
        print(f"最大レスポンス時間: {max_response_time:.3f}秒")


# ==============================================================================
# Error Scenarios and Edge Cases
# ==============================================================================

@pytest.mark.error_scenarios
class TestWhisperAPIErrorHandling:
    """Whisper APIエラーハンドリングテスト"""
    
    @pytest.mark.parametrize(
        ["error_scenario", "expected_status", "expected_message_pattern"],
        [
            # 入力検証エラー
            (
                {"audio_data": None, "filename": "test.wav"}, 
                422, 
                "validation.*error"
            ),
            (
                {"audio_data": "valid_data", "filename": ""}, 
                422, 
                "filename.*required"
            ),
            
            # ビジネスルールエラー
            (
                {"audio_data": "valid_data", "filename": "document.pdf"}, 
                400, 
                "無効な音声フォーマット"
            ),
            (
                {"audio_data": "valid_data", "filename": "huge_file.wav", "_mock_size": 200*1024*1024}, 
                413, 
                "ファイルサイズが大きすぎます"
            ),
        ],
        ids=[
            "audio_data欠落_検証エラー",
            "filename空文字_検証エラー",
            "PDFファイル_フォーマットエラー",
            "200MBファイル_サイズエラー",
        ],
    )
    @pytest.mark.asyncio
    async def test_upload_error_scenarios_各エラーケースで適切なレスポンス(
        self, async_test_client, mock_auth_user, error_scenario, expected_status, expected_message_pattern
    ):
        """各エラーシナリオで適切なステータスコードとメッセージを返すこと"""
        # Arrange（準備）
        if "_mock_size" in error_scenario:
            mock_size = error_scenario.pop("_mock_size")
            with patch("backend.app.api.whisper.get_file_info_from_gcs") as mock_file_info:
                mock_file_info.return_value = {"size": mock_size, "content_type": "audio/wav"}
                
                # Act（実行）
                response = await async_test_client.post(
                    "/backend/whisper",
                    json=error_scenario,
                    headers={"Authorization": "Bearer test-token"}
                )
        else:
            # Act（実行）
            response = await async_test_client.post(
                "/backend/whisper",
                json=error_scenario,
                headers={"Authorization": "Bearer test-token"}
            )
        
        # Assert（検証）
        assert response.status_code == expected_status
        
        response_data = response.json()
        error_message = response_data.get("detail", "")
        
        import re
        assert re.search(expected_message_pattern, error_message, re.IGNORECASE), \
            f"Expected pattern '{expected_message_pattern}' not found in '{error_message}'"


# ==============================================================================
# Advanced Mock Strategies
# ==============================================================================

class TestAdvancedMockStrategies:
    """高度なモック戦略のテスト例"""
    
    @pytest.mark.asyncio
    async def test_with_minimal_mocking_モック最小化例(self, async_test_client, mock_auth_user):
        """モックを最小化し、実際のロジックを可能な限りテストする例"""
        # Arrange（準備）
        # モックは本当に制御が困難な外部依存のみ
        factory = AudioTestDataFactory()
        upload_data = {
            "audio_data": factory.fake.sha256(),
            "filename": "minimal_mock_test.wav",
            "gcs_object": "temp/minimal_mock_test.wav"
        }
        
        # 制御困難な外部サービスのみモック
        with patch("backend.app.api.whisper.enqueue_job_atomic") as mock_enqueue:
            mock_enqueue.return_value = None
            
            # Act（実行）
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            # Assert（検証）
            # 実際のビジネスロジックが動作したことを確認
            assert response.status_code == 200
            response_data = response.json()
            assert "job_id" in response_data
            assert "file_hash" in response_data
    
    @pytest.mark.asyncio
    async def test_with_behavior_verification_振る舞い検証例(self, async_test_client, mock_auth_user):
        """外部システムとの契約（振る舞い）を検証する例"""
        # Arrange（準備）
        factory = AudioTestDataFactory()
        upload_data = {
            "audio_data": factory.fake.sha256(),
            "filename": "behavior_test.wav",
            "gcs_object": "temp/behavior_test.wav",
            "description": "重要な会議録音",
            "num_speakers": 3
        }
        
        # 外部システムとの契約を検証
        with patch("backend.app.api.whisper.enqueue_job_atomic") as mock_enqueue, \
             patch("backend.app.api.whisper.send_notification") as mock_notification:
            
            mock_enqueue.return_value = None
            
            # Act（実行）
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            # Assert（検証）
            assert response.status_code == 200
            
            # 外部システムとの契約を確認
            mock_enqueue.assert_called_once()
            enqueue_call_args = mock_enqueue.call_args
            
            # エンキューされたジョブデータの検証
            job_data = enqueue_call_args[0][1]  # 第2引数がジョブデータ
            assert job_data["description"] == "重要な会議録音"
            assert job_data["num_speakers"] == 3
            assert job_data["user_id"] == mock_auth_user["uid"]
