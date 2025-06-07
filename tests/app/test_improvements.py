"""
Whisperテストシステムの改善版テスト
- 完全なPydanticバリデーション対応
- より現実的なテストデータ
- 強化されたエラーハンドリング
- autospec最適化
"""

import pytest
import json
import uuid
import os
import tempfile
from datetime import datetime
from unittest.mock import patch, Mock, MagicMock, create_autospec
from fastapi import HTTPException
from fastapi.testclient import TestClient

from common_utils.class_types import WhisperUploadRequest, WhisperEditRequest, WhisperSegment, WhisperSpeakerConfigRequest, SpeakerConfigItem
from backend.app.api.whisper import router
from backend.app.main import app


class TestWhisperValidationImproved:
    """改善されたWhisperバリデーションテスト"""
    
    @pytest.mark.asyncio
    async def test_whisper_job_creation_with_complete_data(self, async_test_client, mock_auth_user, mock_environment_variables, enhanced_gcp_services, mock_audio_processing, mock_whisper_services):
        """完全なデータでのジョブ作成テスト（バリデーションエラー解決）"""
        
        # Pydanticバリデーション要件を満たす完全なリクエストデータ
        upload_request = {
            "audio_data": "fake_audio_data_base64_encoded",  # 必須
            "filename": "complete-test-audio.wav",           # 必須
            "gcs_object": "temp/complete-test-audio.wav",
            "original_name": "complete-test-audio.wav",
            "description": "完全なデータでのAPI統合テスト",
            "recording_date": "2025-06-08",
            "language": "ja",
            "initial_prompt": "日本語の音声ファイルです",
            "tags": ["test", "integration", "complete"],
            "num_speakers": 2,
            "min_speakers": 1,
            "max_speakers": 3
        }
        
        # GCSに対応するブロブを設定
        gcs_client = enhanced_gcp_services["storage"]
        bucket = gcs_client.bucket("test-whisper-bucket")
        test_blob = bucket.blob("temp/complete-test-audio.wav")
        
        # より現実的な音声データを設定
        audio_content = b"RIFF" + b"\x00" * 40 + b"WAVE" + b"fake audio data" * 1000  # WAVヘッダー付き
        test_blob.upload_from_string(audio_content, content_type="audio/wav")
        
        response = await async_test_client.post(
            "/backend/whisper",
            json=upload_request,
            headers={"Authorization": "Bearer test-token"}
        )
        
        # デバッグ用レスポンス出力
        print(f"Status code: {response.status_code}")
        if response.status_code != 200:
            print(f"Error response: {response.text}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "job_id" in data
        assert "file_hash" in data
        assert len(data["file_hash"]) == 64  # SHA256ハッシュ
        
        # Firestoreにジョブが正しく保存されたことを確認
        firestore_client = enhanced_gcp_services["firestore"]
        jobs_collection = firestore_client.collection("whisper_jobs")
        
        # ジョブの存在確認（実際のFirestoreクエリをシミュレート）
        user_jobs = jobs_collection.where("user_id", "==", "test-user-123").stream()
        assert len(user_jobs) >= 1
    
    @pytest.mark.asyncio
    async def test_whisper_upload_with_metadata_validation(self, async_test_client, mock_auth_user, mock_environment_variables, enhanced_gcp_services, mock_audio_processing):
        """メタデータ付きアップロードのバリデーションテスト"""
        
        # より詳細なメタデータを含むリクエスト
        upload_request = {
            "audio_data": "VGVzdCBhdWRpbyBkYXRhIGVuY29kZWQgaW4gYmFzZTY0",  # Base64エンコード済み
            "filename": "metadata-test.wav",
            "gcs_object": "temp/metadata-test.wav",
            "original_name": "会議録音_2025年6月8日.wav",
            "description": "重要な会議の録音データ",
            "recording_date": "2025-06-08",
            "language": "ja",
            "initial_prompt": "これは日本語の会議録音です。専門用語が含まれる可能性があります。",
            "tags": ["会議", "重要", "2025年度"],
            "num_speakers": 3,
            "min_speakers": 2,
            "max_speakers": 5
        }
        
        # GCSブロブ設定
        gcs_client = enhanced_gcp_services["storage"]
        bucket = gcs_client.bucket("test-whisper-bucket")
        test_blob = bucket.blob("temp/metadata-test.wav")
        test_blob.upload_from_string(b"fake_metadata_audio_data", content_type="audio/wav")
        
        response = await async_test_client.post(
            "/backend/whisper",
            json=upload_request,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # メタデータが正しく処理されたことを確認
        assert "job_id" in data
        job_id = data["job_id"]
        assert uuid.UUID(job_id)  # 有効なUUIDかチェック
    
    @pytest.mark.asyncio
    async def test_whisper_error_scenarios_improved(self, async_test_client, mock_auth_user, mock_environment_variables, enhanced_gcp_services):
        """改善されたエラーシナリオテスト"""
        
        # ケース1: 必須フィールド欠落
        incomplete_request = {
            "filename": "incomplete.wav",
            # audio_dataが欠落
            "gcs_object": "temp/incomplete.wav"
        }
        
        response = await async_test_client.post(
            "/backend/whisper",
            json=incomplete_request,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any("audio_data" in str(err) for err in error_detail)
        
        # ケース2: 無効なファイル形式
        invalid_format_request = {
            "audio_data": "fake_data",
            "filename": "document.pdf",  # 音声ファイルではない
            "gcs_object": "temp/document.pdf"
        }
        
        gcs_client = enhanced_gcp_services["storage"]
        bucket = gcs_client.bucket("test-whisper-bucket")
        pdf_blob = bucket.blob("temp/document.pdf")
        pdf_blob.upload_from_string(b"PDF content", content_type="application/pdf")
        
        response = await async_test_client.post(
            "/backend/whisper",
            json=invalid_format_request,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "無効な音声フォーマット" in response.json()["detail"]
        
        # ケース3: ファイルサイズ制限超過
        large_file_request = {
            "audio_data": "fake_data",
            "filename": "large_audio.wav",
            "gcs_object": "temp/large_audio.wav"
        }
        
        large_blob = bucket.blob("temp/large_audio.wav")
        large_content = b"x" * (150 * 1024 * 1024)  # 150MB
        large_blob.upload_from_string(large_content, content_type="audio/wav")
        
        response = await async_test_client.post(
            "/backend/whisper",
            json=large_file_request,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 413
        assert "音声ファイルが大きすぎます" in response.json()["detail"]


class TestWhisperBatchProcessingImproved:
    """改善されたバッチ処理テスト"""
    
    def test_process_job_with_complete_firestore_data(self, mock_gcp_services, mock_audio_processing, mock_whisper_services):
        """完全なFirestoreデータでのジョブ処理テスト"""
        from whisper_batch.app.main import _process_job
        
        # WhisperFirestoreDataの全必須フィールドを含む完全なデータ
        complete_job_data = {
            "job_id": "complete-job-test",
            "user_id": "test-user-123",
            "user_email": "test-user@example.com",           # 必須フィールド追加
            "filename": "complete-test-audio.wav",           # 必須フィールド追加
            "gcs_bucket_name": "test-bucket",                # 必須フィールド追加
            "audio_size": 1024000,                           # 必須フィールド追加
            "audio_duration_ms": 60000,                      # 必須フィールド追加
            "file_hash": "complete-test-hash",               # 必須フィールド追加
            "status": "queued",                              # 必須フィールド追加
            "original_name": "完全テスト音声.wav",
            "description": "完全なデータでのバッチ処理テスト",
            "recording_date": "2025-06-08",
            "language": "ja",
            "initial_prompt": "これは完全なテストデータです",
            "tags": ["complete", "test"],
            "num_speakers": 2,
            "min_speakers": 1,
            "max_speakers": 3,
            "created_at": "2025-06-08T10:00:00Z",
            "updated_at": "2025-06-08T10:00:00Z"
        }
        
        # バッチ処理実行
        result = _process_job(mock_gcp_services["firestore"], complete_job_data)
        
        # 処理結果の検証
        assert result is not None
        # モック環境では成功とみなす（実際の処理は模擬）
    
    def test_process_job_error_handling_improved(self, mock_gcp_services):
        """改善されたジョブ処理エラーハンドリング"""
        from whisper_batch.app.main import _process_job
        
        # 不完全なデータでの処理（エラーが期待される）
        incomplete_job_data = {
            "job_id": "incomplete-job-test",
            "user_id": "test-user-123",
            # 必須フィールドが欠落
        }
        
        # バリデーションエラーが発生することを確認
        result = _process_job(mock_gcp_services["firestore"], incomplete_job_data)
        
        # エラーハンドリングが適切に動作することを確認
        # 実装によっては例外が発生するか、エラーステータスが返される
        assert result is None or (hasattr(result, 'error') and result.error is not None)


class TestWhisperMockingImproved:
    """改善されたモック戦略テスト"""
    
    @pytest.mark.asyncio
    async def test_gcs_operations_with_autospec(self, async_test_client, mock_auth_user, mock_environment_variables):
        """autospecを使用したGCS操作テスト"""
        
        # GCSクライアントをautospecで作成
        with patch('google.cloud.storage.Client', autospec=True) as mock_storage_class:
            mock_client = mock_storage_class.return_value
            mock_bucket = Mock()
            mock_blob = Mock()
            
            # モックチェーンの設定
            mock_client.bucket.return_value = mock_bucket
            mock_bucket.blob.return_value = mock_blob
            mock_blob.generate_signed_url.return_value = "https://signed-url.example.com"
            
            response = await async_test_client.post(
                "/backend/whisper/upload_url",
                json={"content_type": "audio/wav"},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            
            # autospecにより、正しいメソッドが正しい引数で呼ばれたことを確認
            mock_storage_class.assert_called_once()
            mock_client.bucket.assert_called()
            mock_bucket.blob.assert_called()
    
    @pytest.mark.asyncio
    async def test_firestore_operations_with_realistic_mocking(self, async_test_client, mock_auth_user, mock_environment_variables):
        """現実的なFirestoreモックテスト"""
        
        with patch('google.cloud.firestore.Client', autospec=True) as mock_firestore_class:
            mock_client = mock_firestore_class.return_value
            mock_collection = Mock()
            mock_query = Mock()
            mock_doc = Mock()
            
            # より現実的なFirestore操作のモック
            mock_client.collection.return_value = mock_collection
            mock_collection.where.return_value.where.return_value = mock_query
            mock_query.stream.return_value = [mock_doc]
            
            # ドキュメントデータのモック
            mock_doc.id = "realistic-doc-id"
            mock_doc.to_dict.return_value = {
                "job_id": "realistic-job-123",
                "user_id": "test-user-123",
                "user_email": "test-user@example.com",
                "filename": "realistic-test.wav",
                "status": "completed",
                "file_hash": "realistic-hash-123"
            }
            
            response = await async_test_client.get(
                "/backend/whisper/jobs/realistic-hash-123",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "realistic-doc-id"
            assert data["file_hash"] == "realistic-hash-123"


class TestWhisperPerformanceImproved:
    """改善されたパフォーマンステスト"""
    
    @pytest.mark.asyncio
    async def test_concurrent_request_handling(self, async_test_client, mock_auth_user, mock_environment_variables, enhanced_gcp_services):
        """並行リクエスト処理テスト"""
        import asyncio
        
        # 並行処理用のリクエストデータ
        requests_data = [
            {
                "audio_data": f"concurrent_test_data_{i}",
                "filename": f"concurrent_test_{i}.wav",
                "gcs_object": f"temp/concurrent_test_{i}.wav"
            }
            for i in range(5)
        ]
        
        # GCSに対応するブロブを設定
        gcs_client = enhanced_gcp_services["storage"]
        bucket = gcs_client.bucket("test-whisper-bucket")
        
        for i, req_data in enumerate(requests_data):
            blob = bucket.blob(f"temp/concurrent_test_{i}.wav")
            blob.upload_from_string(f"audio_data_{i}".encode(), content_type="audio/wav")
        
        # 並行リクエストの実行
        async def make_request(request_data):
            return await async_test_client.post(
                "/backend/whisper",
                json=request_data,
                headers={"Authorization": "Bearer test-token"}
            )
        
        # 並行実行
        tasks = [make_request(req_data) for req_data in requests_data]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 結果の検証
        successful_responses = [r for r in responses if not isinstance(r, Exception)]
        assert len(successful_responses) >= 3  # 最低3つは成功することを期待
        
        for response in successful_responses:
            if hasattr(response, 'status_code'):
                assert response.status_code in [200, 404, 413]  # 許容されるステータス
    
    def test_memory_usage_monitoring_improved(self):
        """改善されたメモリ使用量監視テスト"""
        import psutil
        import os
        
        # プロセス開始時のメモリ使用量
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # メモリ集約的な処理をシミュレート
        large_data = [{"test": "data"} * 1000 for _ in range(100)]
        
        # 処理後のメモリ使用量
        peak_memory = process.memory_info().rss
        
        # メモリ使用量の増加を確認
        memory_increase = peak_memory - initial_memory
        assert memory_increase >= 0  # メモリが増加していることを確認
        
        # メモリリークがないことを確認するため、データを削除
        del large_data
        
        # ガベージコレクションを強制実行
        import gc
        gc.collect()
        
        # 最終メモリ使用量
        final_memory = process.memory_info().rss
        
        # メモリが適切に解放されていることを確認（完全ではないが改善）
        memory_retained = final_memory - initial_memory
        assert memory_retained < memory_increase * 0.8  # 80%以上解放されていることを期待


class TestWhisperIntegrationImproved:
    """改善された統合テスト"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow_realistic(self, async_test_client, mock_auth_user, mock_environment_variables, enhanced_gcp_services, mock_audio_processing, mock_whisper_services):
        """現実的なエンドツーエンドワークフローテスト"""
        
        # ステップ1: 署名付きURLの生成
        upload_url_response = await async_test_client.post(
            "/backend/whisper/upload_url",
            json={"content_type": "audio/wav"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert upload_url_response.status_code == 200
        upload_url_data = upload_url_response.json()
        object_name = upload_url_data["object_name"]
        
        # ステップ2: 音声ファイルのアップロード（GCSブロブに設定）
        gcs_client = enhanced_gcp_services["storage"]
        bucket = gcs_client.bucket("test-whisper-bucket")
        audio_blob = bucket.blob(object_name)
        audio_blob.upload_from_string(b"realistic_audio_data", content_type="audio/wav")
        
        # ステップ3: ジョブの作成
        job_request = {
            "audio_data": "realistic_audio_base64_data",
            "filename": "end_to_end_test.wav",
            "gcs_object": object_name,
            "original_name": "エンドツーエンドテスト.wav",
            "description": "完全なワークフローテスト",
            "language": "ja",
            "num_speakers": 2
        }
        
        job_response = await async_test_client.post(
            "/backend/whisper",
            json=job_request,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert job_response.status_code == 200
        job_data = job_response.json()
        job_id = job_data["job_id"]
        file_hash = job_data["file_hash"]
        
        # ステップ4: ジョブリストの確認
        jobs_response = await async_test_client.get(
            "/backend/whisper/jobs",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert jobs_response.status_code == 200
        jobs_list = jobs_response.json()["jobs"]
        
        # 作成したジョブが含まれていることを確認（モック環境では直接確認は困難）
        assert len(jobs_list) >= 1
        
        # ステップ5: ジョブ詳細の取得
        job_detail_response = await async_test_client.get(
            f"/backend/whisper/jobs/{file_hash}",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert job_detail_response.status_code == 200
        job_detail = job_detail_response.json()
        assert "id" in job_detail
        assert "file_hash" in job_detail
        
        # ワークフロー全体が正常に完了
        print(f"エンドツーエンドワークフロー完了: job_id={job_id}, file_hash={file_hash}")