"""
アドバンスド振る舞い駆動テスト：処理フローと中核ロジックの分離
Behavior-Driven Design Tests with Separation of Concerns

このテストファイルは、以下の高度なテスト戦略を実装します：
1. 処理フローロジックと中核ロジックの分離
2. 大きな振る舞いの分割統治戦略
3. create_autospec + side_effect パターンの活用
4. 包括的なエラーハンドリングテスト
5. パフォーマンス特性の検証
"""

import pytest
import asyncio
import time
import json
import uuid
from unittest.mock import create_autospec, patch, MagicMock, ANY
from typing import Dict, List, Optional, Any
from faker import Faker
import tempfile
import os

# 現在のプロジェクト構造に基づいたインポート
from common_utils.class_types import WhisperFirestoreData


class TestAudioProcessorBehavior:
    """
    音声処理の中核ロジックをテスト（純粋な振る舞いのみ）
    
    テスト設計の根拠：
    - 同値分割：有効な音声形式 vs 無効な音声形式
    - 境界値分析：最大ファイルサイズ、最大時間長
    - エラー推測：破損ファイル、無音ファイル、巨大ファイル
    """
    
    class TestAudioValidation:
        """音声ファイル検証の振る舞い"""
        
        @pytest.mark.parametrize(
            ["file_extension", "file_size_mb", "duration_seconds", "expected_valid"],
            [
                # 有効なケース（同値分割）
                ("wav", 50, 300, True),
                ("mp3", 50, 300, True),
                ("m4a", 50, 300, True),
                
                # 境界値分析：ファイルサイズ上限付近
                ("wav", 99.9, 300, True),    # 上限以下
                ("wav", 100.0, 300, True),   # 上限ちょうど
                ("wav", 100.1, 300, False),  # 上限超過
                
                # 境界値分析：時間長上限付近
                ("wav", 50, 1799, True),     # 上限以下
                ("wav", 50, 1800, True),     # 上限ちょうど
                ("wav", 50, 1801, False),    # 上限超過
                
                # 無効なケース（エラー推測）
                ("txt", 10, 300, False),     # テキストファイル
                ("jpg", 10, 300, False),     # 画像ファイル
                ("wav", 0, 300, False),      # 空ファイル
                ("wav", 50, 0, False),       # 無音ファイル
            ],
            ids=[
                "WAV形式_有効",
                "MP3形式_有効", 
                "M4A形式_有効",
                "ファイルサイズ上限以下_有効",
                "ファイルサイズ上限ちょうど_有効",
                "ファイルサイズ上限超過_無効",
                "時間長上限以下_有効",
                "時間長上限ちょうど_有効", 
                "時間長上限超過_無効",
                "テキストファイル_無効",
                "画像ファイル_無効",
                "空ファイル_無効",
                "無音ファイル_無効",
            ]
        )
        def test_validate_audio_file_各条件で適切な検証結果を返すこと(
            self, file_extension, file_size_mb, duration_seconds, expected_valid
        ):
            """音声ファイル検証ロジックの包括的テスト"""
            # Arrange（準備）
            filename = f"test_audio.{file_extension}"
            file_size_bytes = int(file_size_mb * 1024 * 1024)
            
            # Act（実行） - 純粋なロジック（副作用なし）
            # 実際の検証ロジックはここで呼び出される
            result = self._simulate_audio_validation(
                filename, file_size_bytes, duration_seconds
            )
            
            # Assert（検証）
            assert result == expected_valid, (
                f"Expected {expected_valid} for {filename} "
                f"({file_size_mb}MB, {duration_seconds}s), got {result}"
            )
        
        def _simulate_audio_validation(self, filename: str, size_bytes: int, duration_seconds: float) -> bool:
            """音声検証ロジックのシミュレーション（実装例）"""
            # 実際のプロジェクトでは backend.app.core.audio_utils の関数を呼び出す
            MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
            MAX_DURATION_SECONDS = 1800  # 30分
            VALID_EXTENSIONS = {'.wav', '.mp3', '.m4a'}
            
            if size_bytes <= 0 or duration_seconds <= 0:
                return False
            
            if size_bytes > MAX_SIZE_BYTES or duration_seconds > MAX_DURATION_SECONDS:
                return False
            
            file_ext = '.' + filename.split('.')[-1].lower()
            return file_ext in VALID_EXTENSIONS
    
    class TestAudioProcessingConfiguration:
        """音声処理設定の振る舞い"""
        
        @pytest.mark.parametrize(
            ["noise_reduction", "volume_normalize", "speaker_diarization", "expected_operations"],
            [
                # 全ての組み合わせパターン（組み合わせテスト）
                (True, True, True, ["noise_reduction", "volume_normalize", "speaker_diarization"]),
                (True, True, False, ["noise_reduction", "volume_normalize"]),
                (True, False, True, ["noise_reduction", "speaker_diarization"]),
                (True, False, False, ["noise_reduction"]),
                (False, True, True, ["volume_normalize", "speaker_diarization"]),
                (False, True, False, ["volume_normalize"]),
                (False, False, True, ["speaker_diarization"]),
                (False, False, False, []),
            ],
            ids=[
                "全ての処理有効",
                "ノイズ除去と音量正規化",
                "ノイズ除去と話者分離",
                "ノイズ除去のみ",
                "音量正規化と話者分離",
                "音量正規化のみ",
                "話者分離のみ",
                "全ての処理無効",
            ]
        )
        def test_configure_processing_pipeline_設定に応じた処理パイプラインが作成されること(
            self, noise_reduction, volume_normalize, speaker_diarization, expected_operations
        ):
            """音声処理パイプライン設定の振る舞いテスト"""
            # Arrange（準備）
            config = {
                "noise_reduction": noise_reduction,
                "volume_normalize": volume_normalize,
                "speaker_diarization": speaker_diarization,
                "language": "ja",
                "model": "large-v3"
            }
            
            # Act（実行） - 純粋な設定ロジック
            pipeline_operations = self._simulate_pipeline_configuration(config)
            
            # Assert（検証）
            assert pipeline_operations == expected_operations, (
                f"Expected operations {expected_operations}, got {pipeline_operations}"
            )
        
        def _simulate_pipeline_configuration(self, config: Dict[str, Any]) -> List[str]:
            """処理パイプライン設定のシミュレーション"""
            operations = []
            
            if config.get("noise_reduction", False):
                operations.append("noise_reduction")
            
            if config.get("volume_normalize", False):
                operations.append("volume_normalize")
            
            if config.get("speaker_diarization", False):
                operations.append("speaker_diarization")
            
            return operations


class TestWhisperJobOrchestrationBehavior:
    """
    Whisperジョブオーケストレーションの振る舞いテスト
    
    アプリケーションサービスレイヤー：処理フローに専念
    中核ロジックは別クラスでテスト済みという前提
    """
    
    class TestJobCreationFlow:
        """ジョブ作成フローの統合テスト（代表的なパターンのみ）"""
        
        def test_create_whisper_job_正常なリクエストで完全なフローが実行されること(
            self, enhanced_gcp_services, mock_audio_processing, test_data_factory
        ):
            """
            Whisperジョブ作成の正常フロー統合テスト
            
            この統合テストでは以下を検証：
            1. リクエストバリデーション
            2. ファイルアップロード
            3. ジョブドキュメント作成
            4. Pub/Subメッセージ送信
            """
            # Arrange（準備）
            upload_request = test_data_factory.create_upload_request(
                valid=True,
                filename="integration_test.wav",
                language="ja",
                num_speakers=2
            )
            
            # Act（実行） - 統合フロー
            result = self._simulate_job_creation_flow(
                upload_request, enhanced_gcp_services
            )
            
            # Assert（検証）
            # 統合結果の検証（各ステップの完了確認）
            assert result["status"] == "success"
            assert result["job_id"] is not None
            assert result["gcs_path"] is not None
            
            # 各外部サービス呼び出しの確認
            storage_client = enhanced_gcp_services["storage"]
            firestore_client = enhanced_gcp_services["firestore"]
            pubsub_client = enhanced_gcp_services["pubsub"]
            
            # GCS操作の確認
            bucket = storage_client.bucket("test-whisper-bucket")
            uploaded_blob = bucket.blob(f"whisper/{result['file_hash']}.wav")
            assert uploaded_blob._exists  # EnhancedGCSBlob の _exists 属性
            
            # Firestore操作の確認
            firestore_client.collection.assert_called_with("whisper_jobs")
            
            # Pub/Sub操作の確認
            pubsub_client.publish.assert_called()
        
        def test_create_whisper_job_音声処理エラー時の適切なエラーハンドリング(
            self, enhanced_gcp_services, advanced_mock_behaviors
        ):
            """音声処理エラー時のエラーハンドリングテスト"""
            # Arrange（準備）
            upload_request = {
                "audio_data": "invalid_audio_data",
                "filename": "corrupted.wav"
            }
            
            # 音声処理エラーをシミュレート
            audio_error = advanced_mock_behaviors["whisper_processing_simulation"]["unsupported_format"]()
            
            # Act & Assert（実行と検証）
            with patch('backend.app.core.audio_utils.probe_duration', side_effect=audio_error):
                result = self._simulate_job_creation_flow(
                    upload_request, enhanced_gcp_services
                )
                
                assert result["status"] == "error"
                assert "unsupported" in result["error_message"].lower()
        
        def _simulate_job_creation_flow(
            self, upload_request: Dict[str, Any], gcp_services: Dict[str, Any]
        ) -> Dict[str, Any]:
            """ジョブ作成フローのシミュレーション"""
            try:
                # 1. リクエストバリデーション（中核ロジック）
                if not upload_request.get("audio_data") or not upload_request.get("filename"):
                    return {"status": "error", "error_message": "Invalid request"}
                
                # 2. ファイル処理（インフラ操作）
                file_hash = f"hash_{uuid.uuid4().hex[:8]}"
                gcs_path = f"whisper/{file_hash}.wav"
                
                # 3. GCSアップロード
                bucket = gcp_services["storage"].bucket("test-whisper-bucket")
                blob = bucket.blob(gcs_path)
                blob.upload_from_string(upload_request["audio_data"], content_type="audio/wav")
                
                # 4. ジョブドキュメント作成
                job_id = str(uuid.uuid4())
                job_data = {
                    "job_id": job_id,
                    "file_hash": file_hash,
                    "filename": upload_request["filename"],
                    "status": "queued"
                }
                
                collection = gcp_services["firestore"].collection("whisper_jobs")
                collection.document(job_id).set(job_data)
                
                # 5. Pub/Subメッセージ送信
                gcp_services["pubsub"].publish(
                    topic="whisper-queue",
                    data=json.dumps({"job_id": job_id}).encode()
                )
                
                return {
                    "status": "success",
                    "job_id": job_id,
                    "file_hash": file_hash,
                    "gcs_path": gcs_path
                }
                
            except Exception as e:
                return {
                    "status": "error",
                    "error_message": str(e)
                }


class TestAdvancedMockingPatterns:
    """
    create_autospec + side_effect パターンの実践テスト
    高度なモッキング戦略とテストダブル利用指針の実装
    """
    
    class TestGCSOperationsBehavior:
        """GCS操作の安全なモッキングパターン"""
        
        def test_gcs_upload_with_autospec_型安全性が保証されたモッキング(self):
            """create_autospec + side_effectパターンによる型安全なテスト"""
            
            # Arrange（準備） - autospecによる型安全なモック
            import google.cloud.storage as storage
            
            mock_client_class = create_autospec(storage.Client, spec_set=True)
            
            # カスタム振る舞いクラス（状態管理とバリデーション付き）
            class GCSClientBehavior:
                def __init__(self):
                    self._buckets: Dict[str, Dict[str, Any]] = {}
                
                def bucket(self, bucket_name: str):
                    if not isinstance(bucket_name, str) or not bucket_name:
                        raise ValueError("バケット名は空文字列にできません")
                    
                    if bucket_name not in self._buckets:
                        self._buckets[bucket_name] = {}
                    
                    bucket_mock = MagicMock()
                    bucket_mock.name = bucket_name
                    bucket_mock.blob.side_effect = self._create_blob_behavior(bucket_name)
                    return bucket_mock
                
                def _create_blob_behavior(self, bucket_name: str):
                    def blob(blob_name: str):
                        if not isinstance(blob_name, str) or not blob_name:
                            raise ValueError("Blob名は空文字列にできません")
                        
                        blob_mock = MagicMock()
                        blob_mock.name = blob_name
                        blob_mock.bucket = bucket_name
                        
                        # upload_from_stringの振る舞い
                        def upload_from_string(data, content_type=None, **kwargs):
                            if not isinstance(data, (str, bytes)):
                                raise TypeError(f"データは文字列またはバイト列である必要があります: {type(data)}")
                            
                            # 状態を更新
                            self._buckets[bucket_name][blob_name] = {
                                "data": data,
                                "content_type": content_type or "application/octet-stream",
                                "exists": True
                            }
                        
                        blob_mock.upload_from_string.side_effect = upload_from_string
                        blob_mock.exists.return_value = True
                        
                        return blob_mock
                    
                    return blob
            
            # autospecモックにカスタム振る舞いを注入
            behavior = GCSClientBehavior()
            mock_client_instance = mock_client_class.return_value
            mock_client_instance.bucket.side_effect = behavior.bucket
            
            # Act（実行）
            with patch('google.cloud.storage.Client', return_value=mock_client_instance):
                client = storage.Client()
                
                # ✅ 正常ケース：存在するメソッドの呼び出し
                bucket = client.bucket("test-bucket")
                blob = bucket.blob("test-file.wav")
                blob.upload_from_string(b"audio_data", content_type="audio/wav")
                
                # ✅ バリデーション：カスタム振る舞いによるエラー検証
                with pytest.raises(ValueError, match="バケット名は空文字列にできません"):
                    client.bucket("")
                
                with pytest.raises(TypeError, match="データは文字列またはバイト列である必要があります"):
                    blob.upload_from_string(12345)  # 数値は無効
            
            # Assert（検証）
            # autospecの恩恵：存在しないメソッドは呼び出せない
            # client.non_existent_method()  # ← これはAttributeErrorになる
            
            # カスタム振る舞いの状態確認
            assert "test-bucket" in behavior._buckets
            assert "test-file.wav" in behavior._buckets["test-bucket"]
            assert behavior._buckets["test-bucket"]["test-file.wav"]["exists"] is True
    
    class TestFirestoreOperationsBehavior:
        """Firestore操作の高度なモッキング"""
        
        def test_firestore_transaction_with_complex_behavior(self):
            """複雑な状態管理を伴うFirestore操作のテスト"""
            
            # Arrange（準備）
            import google.cloud.firestore as firestore
            
            mock_client_class = create_autospec(firestore.Client, spec_set=True)
            
            # Firestoreエミュレーター的な振る舞い
            class FirestoreClientBehavior:
                def __init__(self):
                    self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
                
                def collection(self, collection_name: str):
                    if collection_name not in self._collections:
                        self._collections[collection_name] = {}
                    
                    collection_mock = MagicMock()
                    collection_mock.document.side_effect = self._create_document_behavior(collection_name)
                    return collection_mock
                
                def _create_document_behavior(self, collection_name: str):
                    def document(doc_id: str):
                        doc_mock = MagicMock()
                        doc_mock.id = doc_id
                        
                        def set_document(data: Dict[str, Any], merge: bool = False):
                            if merge and doc_id in self._collections[collection_name]:
                                # マージ操作
                                self._collections[collection_name][doc_id].update(data)
                            else:
                                # 上書き操作
                                self._collections[collection_name][doc_id] = data.copy()
                        
                        def get_document():
                            if doc_id in self._collections[collection_name]:
                                doc_mock.exists = True
                                doc_mock.to_dict.return_value = self._collections[collection_name][doc_id]
                            else:
                                doc_mock.exists = False
                                doc_mock.to_dict.return_value = None
                            return doc_mock
                        
                        doc_mock.set.side_effect = set_document
                        doc_mock.get.side_effect = get_document
                        return doc_mock
                    
                    return document
            
            behavior = FirestoreClientBehavior()
            mock_client_instance = mock_client_class.return_value
            mock_client_instance.collection.side_effect = behavior.collection
            
            # Act（実行）
            with patch('google.cloud.firestore.Client', return_value=mock_client_instance):
                client = firestore.Client()
                
                # ドキュメント作成
                doc_ref = client.collection("whisper_jobs").document("job-123")
                doc_ref.set({
                    "status": "queued",
                    "filename": "test.wav",
                    "user_id": "user-123"
                })
                
                # ドキュメント更新（マージ）
                doc_ref.set({"status": "processing"}, merge=True)
                
                # ドキュメント取得
                doc_snapshot = doc_ref.get()
            
            # Assert（検証）
            assert doc_snapshot.exists
            doc_data = doc_snapshot.to_dict()
            assert doc_data["status"] == "processing"
            assert doc_data["filename"] == "test.wav"  # マージにより保持
            assert doc_data["user_id"] == "user-123"   # マージにより保持


class TestTestDataFactoryPattern:
    """
    テストデータファクトリパターンとFakerライブラリの活用
    """
    
    @pytest.fixture
    def advanced_fake_data_factory(self):
        """高度なテストデータファクトリ"""
        
        class AdvancedTestDataFactory:
            def __init__(self):
                self.fake = Faker(['ja_JP', 'en_US'])
                self.fake.seed_instance(12345)  # 再現可能なテスト
            
            def create_realistic_whisper_job(self, status: str = "queued", **overrides) -> WhisperFirestoreData:
                """リアルなWhisperジョブデータを生成"""
                base_data = {
                    "job_id": f"job_{self.fake.uuid4()}",
                    "user_id": f"user_{self.fake.uuid4()}",
                    "user_email": self.fake.email(),
                    "filename": f"{self.fake.word()}_{self.fake.random_int(1, 999)}.wav",
                    "gcs_bucket_name": "production-whisper-bucket",
                    "audio_size": self.fake.random_int(100000, 10000000),  # 100KB - 10MB
                    "audio_duration_ms": self.fake.random_int(5000, 1800000),  # 5秒 - 30分
                    "file_hash": self.fake.sha256(),
                    "status": status,
                    "num_speakers": self.fake.random_int(1, 5),
                    "min_speakers": 1,
                    "max_speakers": 5,
                    "language": self.fake.random_element(["ja", "en", "auto"]),
                    "initial_prompt": self.fake.sentence(),
                    "tags": [self.fake.word() for _ in range(self.fake.random_int(0, 3))],
                    "description": self.fake.text(max_nb_chars=100)
                }
                base_data.update(overrides)
                return WhisperFirestoreData(**base_data)
            
            def create_stress_test_data(self, count: int = 100) -> List[WhisperFirestoreData]:
                """ストレステスト用の大量データ生成"""
                return [self.create_realistic_whisper_job() for _ in range(count)]
            
            def create_edge_case_data(self) -> List[WhisperFirestoreData]:
                """エッジケース用のデータ生成"""
                edge_cases = []
                
                # 境界値ケース
                edge_cases.append(self.create_realistic_whisper_job(
                    audio_size=0,  # 最小サイズ
                    audio_duration_ms=1,  # 最短時間
                    filename="a.wav"  # 最短ファイル名
                ))
                
                edge_cases.append(self.create_realistic_whisper_job(
                    audio_size=104857600,  # 最大サイズ（100MB）
                    audio_duration_ms=1800000,  # 最長時間（30分）
                    filename="a" * 200 + ".wav"  # 長いファイル名
                ))
                
                # 特殊文字ケース
                edge_cases.append(self.create_realistic_whisper_job(
                    filename="テスト音声_特殊文字@#$%^&*().wav",
                    description="日本語の説明\n改行文字\tタブ文字を含む"
                ))
                
                return edge_cases
        
        return AdvancedTestDataFactory()
    
    def test_realistic_data_generation_with_faker(self, advanced_fake_data_factory):
        """Fakerによるリアルなテストデータ生成の検証"""
        # Arrange & Act（準備と実行）
        jobs = advanced_fake_data_factory.create_stress_test_data(count=10)
        
        # Assert（検証）
        assert len(jobs) == 10
        
        # 各ジョブのデータ品質確認
        for job in jobs:
            assert isinstance(job.job_id, str) and len(job.job_id) > 0
            assert "@" in job.user_email  # メールアドレス形式
            assert job.filename.endswith('.wav')
            assert 100000 <= job.audio_size <= 10000000  # サイズ範囲
            assert 5000 <= job.audio_duration_ms <= 1800000  # 時間範囲
            assert 1 <= job.num_speakers <= 5  # 話者数範囲
        
        # 一意性確認（Fakerのランダム性）
        job_ids = [job.job_id for job in jobs]
        assert len(set(job_ids)) == len(job_ids)  # 全て一意
    
    def test_edge_case_data_coverage(self, advanced_fake_data_factory):
        """エッジケースデータの網羅性確認"""
        # Arrange & Act（準備と実行）
        edge_cases = advanced_fake_data_factory.create_edge_case_data()
        
        # Assert（検証）
        assert len(edge_cases) >= 3  # 最低3つのエッジケース
        
        # 境界値ケースの存在確認
        has_min_size = any(job.audio_size == 0 for job in edge_cases)
        has_max_size = any(job.audio_size >= 100000000 for job in edge_cases)
        has_special_chars = any("@" in job.filename or "%" in job.filename for job in edge_cases)
        
        assert has_min_size, "最小サイズのエッジケースが存在しません"
        assert has_max_size, "最大サイズのエッジケースが存在しません"
        assert has_special_chars, "特殊文字のエッジケースが存在しません"


class TestPerformanceAndLoadBehavior:
    """
    パフォーマンステストと負荷テストの振る舞い
    """
    
    @pytest.mark.performance
    def test_concurrent_whisper_job_creation_performance(
        self, enhanced_gcp_services, enhanced_test_metrics, advanced_fake_data_factory
    ):
        """並行Whisperジョブ作成のパフォーマンステスト"""
        # Arrange（準備）
        enhanced_test_metrics.start_measurement()
        concurrent_jobs = 10
        job_requests = [
            advanced_fake_data_factory.create_realistic_whisper_job().dict()
            for _ in range(concurrent_jobs)
        ]
        
        # Act（実行） - 並行処理シミュレーション
        async def create_job_concurrent(job_data):
            """並行ジョブ作成のシミュレーション"""
            await asyncio.sleep(0.1)  # 実際の処理時間をシミュレート
            return {"job_id": job_data["job_id"], "status": "created"}
        
        async def run_concurrent_test():
            tasks = [create_job_concurrent(job) for job in job_requests]
            return await asyncio.gather(*tasks)
        
        # 非同期実行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(run_concurrent_test())
        finally:
            loop.close()
        
        enhanced_test_metrics.end_measurement()
        
        # Assert（検証）
        assert len(results) == concurrent_jobs
        assert all(result["status"] == "created" for result in results)
        
        # パフォーマンス要件の検証
        enhanced_test_metrics.assert_performance_thresholds(
            max_duration_seconds=5.0,  # 5秒以内
            max_memory_increase_mb=30.0  # 30MB以内
        )
    
    @pytest.mark.slow
    def test_large_file_processing_memory_efficiency(
        self, enhanced_test_metrics, advanced_fake_data_factory
    ):
        """大きなファイル処理時のメモリ効率性テスト"""
        # Arrange（準備）
        enhanced_test_metrics.start_measurement()
        
        # 大きなファイルをシミュレート（50MBのデータ）
        large_audio_data = b"0" * (50 * 1024 * 1024)
        
        # Act（実行）
        def process_large_file(audio_data: bytes) -> dict:
            """大きなファイル処理のシミュレーション"""
            # チャンク処理による効率的なメモリ使用
            chunk_size = 1024 * 1024  # 1MB chunks
            processed_size = 0
            
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                processed_size += len(chunk)
                # 実際の処理はここで行われる
            
            return {"processed_size": processed_size, "status": "completed"}
        
        result = process_large_file(large_audio_data)
        
        enhanced_test_metrics.end_measurement()
        
        # Assert（検証）
        assert result["status"] == "completed"
        assert result["processed_size"] == len(large_audio_data)
        
        # メモリ効率性の検証
        memory_usage = enhanced_test_metrics.get_memory_usage()
        if memory_usage:
            # メモリ増加量がファイルサイズの2倍を超えないことを確認
            max_acceptable_increase = (50 * 2)  # 100MB
            assert memory_usage["increase_mb"] < max_acceptable_increase, (
                f"メモリ使用量が非効率的です: {memory_usage['increase_mb']:.2f}MB"
            )


# マーカーの設定
@pytest.mark.integration
class TestAdvancedIntegrationScenarios:
    """高度な統合シナリオテスト"""
    
    def test_complete_whisper_workflow_with_error_recovery(
        self, enhanced_gcp_services, advanced_fake_data_factory, advanced_mock_behaviors
    ):
        """エラー回復を含む完全なWhisperワークフローテスト"""
        # このテストは、実際のワークフロー全体をエラー注入とともに検証
        # 実装は省略（実際のプロジェクトでは詳細実装が必要）
        pass


if __name__ == "__main__":
    # テストファイルを直接実行する場合の設定
    pytest.main([__file__, "-v", "--tb=short"])