"""
Whisper API エンドポイントのテスト
"""

import pytest
import json
import uuid
from unittest.mock import patch, Mock, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
import os
import tempfile
from pathlib import Path

from common_utils.class_types import WhisperUploadRequest, WhisperEditRequest, WhisperSegment, WhisperSpeakerConfigRequest, SpeakerConfigItem
from backend.app.api.whisper import router
from backend.app.main import app


class TestWhisperUploadUrl:
    """署名付きURL生成のテスト"""
    
    @pytest.mark.asyncio
    async def test_create_upload_url_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """署名付きURL生成の成功ケース"""
        with patch("google.cloud.storage.Client") as mock_storage:
            # GCSクライアントのモック
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.post(
                "/whisper/upload_url",
                json={"content_type": "audio/wav"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "upload_url" in data
            assert "object_name" in data
            assert data["upload_url"] == "https://storage.googleapis.com/signed-url"
            assert data["object_name"].startswith("whisper/test-user-123/")
    
    @pytest.mark.asyncio
    async def test_create_upload_url_without_auth(self, async_test_client, mock_environment_variables):
        """認証なしでのURL生成（失敗ケース）"""
        response = await async_test_client.post(
            "/whisper/upload_url",
            json={"content_type": "audio/wav"}
        )
        
        assert response.status_code == 401


class TestWhisperUpload:
    """音声アップロードとジョブ作成のテスト"""
    
    @pytest.mark.asyncio
    async def test_upload_audio_success(self, async_test_client, mock_auth_user, mock_environment_variables, sample_audio_file):
        """音声アップロードの成功ケース"""
        # テスト用のリクエストデータ
        upload_request = {
            "gcs_object": "temp/test-audio.wav",
            "original_name": "test-audio.wav",
            "description": "テスト用音声",
            "recording_date": "2025-05-29",
            "language": "ja",
            "initial_prompt": "",
            "tags": ["test"],
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1
        }
        
        with patch.multiple(
            "backend.app.api.whisper",
            storage=Mock(),
            firestore=Mock(),
            tempfile=Mock()
        ):
            # GCSモック
            mock_storage_client = Mock()
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.content_type = "audio/wav"
            mock_blob.size = 44100
            mock_bucket.blob.return_value = mock_blob
            mock_storage_client.bucket.return_value = mock_bucket
            
            # Firestoreモック
            mock_firestore_client = Mock()
            
            # 音声処理のモック
            with patch("backend.app.api.whisper.probe_duration", return_value=1.0), \
                 patch("backend.app.api.whisper.convert_audio_to_wav_16k_mono"), \
                 patch("backend.app.api.whisper.enqueue_job_atomic"), \
                 patch("backend.app.api.whisper.trigger_whisper_batch_processing"), \
                 patch("google.cloud.storage.Client", return_value=mock_storage_client), \
                 patch("google.cloud.firestore.Client", return_value=mock_firestore_client), \
                 patch("tempfile.NamedTemporaryFile") as mock_tempfile, \
                 patch("os.path.getsize", return_value=44100), \
                 patch("os.remove"):
                
                # 一時ファイルのモック
                mock_temp_file = Mock()
                mock_temp_file.name = "/tmp/test_audio.wav"
                mock_tempfile.return_value.__enter__.return_value = mock_temp_file
                
                response = await async_test_client.post(
                    "/whisper",
                    json=upload_request
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "job_id" in data
                assert "file_hash" in data
    
    @pytest.mark.asyncio
    async def test_upload_audio_file_too_large(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ファイルサイズが大きすぎる場合のテスト"""
        upload_request = {
            "gcs_object": "temp/large-audio.wav",
            "original_name": "large-audio.wav"
        }
        
        with patch("google.cloud.storage.Client") as mock_storage:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.content_type = "audio/wav"
            mock_blob.size = 200 * 1024 * 1024  # 200MB（制限を超える）
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.post(
                "/whisper",
                json=upload_request
            )
            
            assert response.status_code == 413
            assert "音声ファイルが大きすぎます" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_upload_audio_invalid_format(self, async_test_client, mock_auth_user, mock_environment_variables):
        """無効な音声フォーマットの場合のテスト"""
        upload_request = {
            "gcs_object": "temp/test-document.pdf",
            "original_name": "test-document.pdf"
        }
        
        with patch("google.cloud.storage.Client") as mock_storage:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.content_type = "application/pdf"
            mock_blob.size = 1024
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.post(
                "/whisper",
                json=upload_request
            )
            
            assert response.status_code == 400
            assert "無効な音声フォーマット" in response.json()["detail"]


class TestWhisperJobsList:
    """ジョブ一覧取得のテスト"""
    
    @pytest.mark.asyncio
    async def test_list_jobs_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ジョブ一覧取得の成功ケース"""
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("backend.app.api.whisper.check_and_update_timeout_jobs"), \
             patch("backend.app.api.whisper._get_current_processing_job_count", return_value=0), \
             patch("backend.app.api.whisper._get_env_var", return_value="5"):
            
            # モックジョブデータ
            mock_job_doc = Mock()
            mock_job_doc.id = "job-123"
            mock_job_doc.to_dict.return_value = {
                "user_email": "test-user@example.com",
                "filename": "test.wav",
                "status": "completed",
                "created_at": "2025-05-29T10:00:00Z"
            }
            
            mock_collection = Mock()
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection.where.return_value.where.return_value.order_by.return_value.limit.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            response = await async_test_client.get("/whisper/jobs")
            
            assert response.status_code == 200
            data = response.json()
            assert "jobs" in data
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["id"] == "job-123"
    
    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ステータスフィルターを使ったジョブ一覧取得"""
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("backend.app.api.whisper.check_and_update_timeout_jobs"), \
             patch("backend.app.api.whisper._get_current_processing_job_count", return_value=5), \
             patch("backend.app.api.whisper._get_env_var", return_value="5"):
            
            mock_collection = Mock()
            mock_query = Mock()
            mock_query.stream.return_value = []
            mock_collection.where.return_value.where.return_value.where.return_value.order_by.return_value.limit.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            response = await async_test_client.get("/whisper/jobs?status=completed&limit=10")
            
            assert response.status_code == 200


class TestWhisperJobOperations:
    """ジョブ操作のテスト"""
    
    @pytest.mark.asyncio
    async def test_get_job_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ジョブ詳細取得の成功ケース"""
        file_hash = "test-hash-123"
        
        with patch("google.cloud.firestore.Client") as mock_firestore:
            mock_job_doc = Mock()
            mock_job_doc.id = "job-123"
            mock_job_doc.to_dict.return_value = {
                "file_hash": file_hash,
                "filename": "test.wav",
                "status": "completed"
            }
            
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            response = await async_test_client.get(f"/whisper/jobs/{file_hash}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "job-123"
            assert data["file_hash"] == file_hash
    
    @pytest.mark.asyncio
    async def test_get_job_not_found(self, async_test_client, mock_auth_user, mock_environment_variables):
        """存在しないジョブの取得"""
        file_hash = "nonexistent-hash"
        
        with patch("google.cloud.firestore.Client") as mock_firestore:
            mock_query = Mock()
            mock_query.stream.return_value = []
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            response = await async_test_client.get(f"/whisper/jobs/{file_hash}")
            
            assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_cancel_job_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ジョブキャンセルの成功ケース"""
        file_hash = "test-hash-123"
        
        with patch("backend.app.api.whisper._update_job_status", return_value="job-123"):
            response = await async_test_client.post(f"/whisper/jobs/{file_hash}/cancel")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "canceled"
            assert data["job_id"] == "job-123"
    
    @pytest.mark.asyncio
    async def test_retry_job_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ジョブ再実行の成功ケース"""
        file_hash = "test-hash-123"
        
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("backend.app.api.whisper.trigger_whisper_batch_processing"):
            
            mock_job_doc = Mock()
            mock_job_doc.id = "job-123"
            mock_job_doc.to_dict.return_value = {"status": "failed"}
            mock_job_doc.reference = Mock()
            
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value.limit.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            response = await async_test_client.post(f"/whisper/jobs/{file_hash}/retry")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued_for_retry"


class TestWhisperTranscript:
    """文字起こし結果の取得・編集のテスト"""
    
    @pytest.mark.asyncio
    async def test_get_original_transcript_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """元の文字起こし結果取得の成功ケース"""
        file_hash = "test-hash-123"
        transcript_data = [
            {"start": 0.0, "end": 1.0, "text": "こんにちは", "speaker": "SPEAKER_01"}
        ]
        
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("google.cloud.storage.Client") as mock_storage:
            
            # Firestoreモック（権限確認用）
            mock_job_doc = Mock()
            mock_job_doc.to_dict.return_value = {"file_hash": file_hash}
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            # GCSモック
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.download_as_text.return_value = json.dumps(transcript_data)
            mock_bucket = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.get(f"/whisper/transcript/{file_hash}/original")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["text"] == "こんにちは"
    
    @pytest.mark.asyncio
    async def test_edit_job_transcript_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """文字起こし結果編集の成功ケース"""
        file_hash = "test-hash-123"
        edit_request = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "編集済みテキスト",
                    "speaker": "SPEAKER_01"
                }
            ]
        }
        
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("google.cloud.storage.Client") as mock_storage:
            
            # Firestoreモック
            mock_job_doc = Mock()
            mock_job_doc.id = "job-123"
            mock_job_doc.reference = Mock()
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            # GCSモック
            mock_blob = Mock()
            mock_bucket = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.post(
                f"/whisper/jobs/{file_hash}/edit",
                json=edit_request
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "gcs_path" in data


class TestWhisperSpeakerConfig:
    """スピーカー設定のテスト"""
    
    @pytest.mark.asyncio
    async def test_save_speaker_config_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """スピーカー設定保存の成功ケース"""
        file_hash = "test-hash-123"
        speaker_config_request = {
            "speaker_config": {
                "SPEAKER_01": {
                    "name": "話者1",
                    "color": "#FF0000"
                },
                "SPEAKER_02": {
                    "name": "話者2",
                    "color": "#00FF00"
                }
            }
        }
        
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("google.cloud.storage.Client") as mock_storage:
            
            # Firestoreモック
            mock_job_doc = Mock()
            mock_job_doc.id = "job-123"
            mock_job_doc.reference = Mock()
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            # GCSモック
            mock_blob = Mock()
            mock_bucket = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.post(
                f"/whisper/jobs/{file_hash}/speaker_config",
                json=speaker_config_request
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_get_speaker_config_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """スピーカー設定取得の成功ケース"""
        file_hash = "test-hash-123"
        speaker_config = {
            "SPEAKER_01": {"name": "話者1", "color": "#FF0000"}
        }
        
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("google.cloud.storage.Client") as mock_storage:
            
            # Firestoreモック（権限確認用）
            mock_job_doc = Mock()
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            # GCSモック
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.download_as_text.return_value = json.dumps(speaker_config)
            mock_bucket = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.get(f"/whisper/jobs/{file_hash}/speaker_config")
            
            assert response.status_code == 200
            data = response.json()
            assert "SPEAKER_01" in data
            assert data["SPEAKER_01"]["name"] == "話者1"
    
    @pytest.mark.asyncio
    async def test_get_speaker_config_not_found(self, async_test_client, mock_auth_user, mock_environment_variables):
        """スピーカー設定が存在しない場合"""
        file_hash = "test-hash-123"
        
        with patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("google.cloud.storage.Client") as mock_storage:
            
            # Firestoreモック（権限確認用）
            mock_job_doc = Mock()
            mock_query = Mock()
            mock_query.stream.return_value = [mock_job_doc]
            mock_collection = Mock()
            mock_collection.where.return_value.where.return_value = mock_query
            mock_firestore.return_value.collection.return_value = mock_collection
            
            # GCSモック（ファイルが存在しない）
            mock_blob = Mock()
            mock_blob.exists.return_value = False
            mock_bucket = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.get(f"/whisper/jobs/{file_hash}/speaker_config")
            
            assert response.status_code == 200
            data = response.json()
            assert data == {}  # 空のオブジェクトが返される
