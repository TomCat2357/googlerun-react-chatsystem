"""
Whisper API エンドポイントのテスト

このファイルでは主にモック中心のテストを行いますが、
一部のテストでGCPエミュレータの使用例も示しています。
エミュレータを使用するテストは @pytest.mark.emulator でマークされています。
"""

import pytest
import json
import uuid
from unittest.mock import patch, Mock, MagicMock, create_autospec
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
    
    def test_create_upload_url_success(self, test_client, mock_auth_user, mock_environment_variables):
        """署名付きURL生成の成功ケース"""
        with patch("google.cloud.storage.Client") as mock_storage:
            # GCSクライアントのモック
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = test_client.post(
                "/backend/whisper/upload_url",
                json={"content_type": "audio/wav"},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "upload_url" in data
            assert "object_name" in data
            assert data["upload_url"] == "https://storage.googleapis.com/signed-url"
            assert data["object_name"].startswith("whisper/test-user-123/")
    
    def test_create_upload_url_without_auth(self, test_client, mock_environment_variables):
        """認証なしでのURL生成（失敗ケース）"""
        response = test_client.post(
            "/backend/whisper/upload_url",
            json={"content_type": "audio/wav"}
        )
        
        assert response.status_code == 401


class TestWhisperUpload:
    """音声アップロードとジョブ作成のテスト"""
    
    @pytest.mark.asyncio
    async def test_upload_audio_success(self, async_test_client, mock_auth_user, mock_environment_variables, sample_audio_file):
        """音声アップロードの成功ケース"""
        # テスト用のリクエストデータ（実装に合わせてフィールドを追加）
        upload_request = {
            "audio_data": "dummy_base64_data",  # WhisperUploadRequestで必要
            "filename": "test-audio.wav",       # WhisperUploadRequestで必要
            "gcs_object": "temp/test-audio.wav", # 実装で使用
            "original_name": "test-audio.wav",   # 実装で使用
            "description": "テスト用音声",
            "recording_date": "2025-05-29",
            "language": "ja",
            "initial_prompt": "",
            "tags": ["test"],
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1
        }
        
        # subprocess.Popenを直接モック化してffprobeとffmpegの問題を回避
        mock_process = Mock()
        mock_process.communicate.return_value = (b"1.0", b"")  # duration=1.0秒
        mock_process.returncode = 0
        
        with patch('subprocess.Popen', return_value=mock_process), \
             patch("google.cloud.storage.Client") as mock_storage, \
             patch("google.cloud.firestore.Client") as mock_firestore, \
             patch("backend.app.api.whisper.enqueue_job_atomic") as mock_enqueue, \
             patch("fastapi.BackgroundTasks.add_task") as mock_add_task:
            
            # GCSクライアントのモック
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.content_type = "audio/wav"
            mock_blob.size = 44100
            mock_blob.reload.return_value = None
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            # Firestoreのモック
            mock_doc_ref = Mock()
            mock_doc_ref.id = "test-job-123"
            mock_collection = Mock()
            mock_collection.add.return_value = (None, mock_doc_ref)
            mock_firestore.return_value.collection.return_value = mock_collection
            
            # ジョブエンキューのモック
            mock_enqueue.return_value = None
            
            # BackgroundTasksのadd_taskメソッドをモック化してバックグラウンド実行を無効化
            mock_add_task.return_value = None
            
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_request,
                headers={"Authorization": "Bearer test-token"}
            )
        
        # デバッグ用：レスポンス内容を表示
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "job_id" in data
        assert "file_hash" in data
    
    @pytest.mark.asyncio
    async def test_upload_audio_file_too_large(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ファイルサイズが大きすぎる場合のテスト"""
        upload_request = {
            "audio_data": "dummy_base64_data",  # 必須フィールド
            "filename": "large-audio.wav",     # 必須フィールド
            "gcs_object": "temp/large-audio.wav",
            "original_name": "large-audio.wav"
        }
        
        with patch("google.cloud.storage.Client") as mock_storage:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.content_type = "audio/wav"
            mock_blob.size = 200 * 1024 * 1024  # 200MB（制限を超える）
            mock_blob.reload.return_value = None
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_request,
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 413
            assert "音声ファイルが大きすぎます" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_upload_audio_invalid_format(self, async_test_client, mock_auth_user, mock_environment_variables):
        """無効な音声フォーマットの場合のテスト"""
        upload_request = {
            "audio_data": "dummy_base64_data",  # 必須フィールド
            "filename": "test-document.pdf",   # 必須フィールド
            "gcs_object": "temp/test-document.pdf",
            "original_name": "test-document.pdf"
        }
        
        with patch("google.cloud.storage.Client") as mock_storage:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.content_type = "application/pdf"
            mock_blob.size = 1024
            mock_blob.reload.return_value = None
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_request,
                headers={"Authorization": "Bearer test-token"}
            )
            
            # デバッグ用：レスポンス内容を表示
            print(f"Status code: {response.status_code}")
            print(f"Response: {response.text}")
            
            assert response.status_code == 400
            assert "無効な音声フォーマット" in response.json()["detail"]


class TestWhisperJobsList:
    """ジョブ一覧取得のテスト"""
    
    @pytest.mark.asyncio
    async def test_list_jobs_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ジョブ一覧取得の成功ケース"""
        
        # check_and_update_timeout_jobsをモック化（問題の原因）
        async def mock_check_and_update_timeout_jobs(db):
            """タイムアウトジョブチェック関数のモック"""
            pass
            
        with patch("backend.app.api.whisper.check_and_update_timeout_jobs", side_effect=mock_check_and_update_timeout_jobs), \
             patch("backend.app.api.whisper._get_current_processing_job_count", return_value=0), \
             patch("backend.app.api.whisper._get_env_var", return_value="5"):
            
            response = await async_test_client.get(
                "/backend/whisper/jobs",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "jobs" in data
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["id"] == "test-doc-id"  # conftest.pyで設定したIDに合わせる
    
    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ステータスフィルターを使ったジョブ一覧取得"""
        
        # check_and_update_timeout_jobsをモック化
        async def mock_check_and_update_timeout_jobs(db):
            """タイムアウトジョブチェック関数のモック"""
            pass
            
        with patch("backend.app.api.whisper.check_and_update_timeout_jobs", side_effect=mock_check_and_update_timeout_jobs), \
             patch("backend.app.api.whisper._get_current_processing_job_count", return_value=5), \
             patch("backend.app.api.whisper._get_env_var", return_value="5"):
            
            response = await async_test_client.get(
                "/backend/whisper/jobs?status=completed&limit=10",
                headers={"Authorization": "Bearer test-token"}
            )
            
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
            
            response = await async_test_client.get(
                f"/backend/whisper/jobs/{file_hash}",
                headers={"Authorization": "Bearer test-token"}
            )
            
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
            
            response = await async_test_client.get(
                f"/backend/whisper/jobs/{file_hash}",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_cancel_job_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ジョブキャンセルの成功ケース"""
        file_hash = "test-hash-123"
        
        with patch("backend.app.api.whisper._update_job_status", return_value="test-doc-id"):
            response = await async_test_client.post(
                f"/backend/whisper/jobs/{file_hash}/cancel",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "canceled"
            assert data["job_id"] == "test-doc-id"  # conftest.pyで設定したIDに合わせる
    
    @pytest.mark.asyncio
    async def test_retry_job_success(self, async_test_client, mock_auth_user, mock_environment_variables):
        """ジョブ再実行の成功ケース"""
        file_hash = "test-hash-123"
        
        # trigger_whisper_batch_processing を適切にモック化
        async def mock_trigger_batch_processing(job_id: str, background_tasks):
            """バッチ処理トリガー関数のモック"""
            pass
        
        with patch("backend.app.api.whisper.trigger_whisper_batch_processing", side_effect=mock_trigger_batch_processing):
            
            response = await async_test_client.post(
                f"/backend/whisper/jobs/{file_hash}/retry",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued_for_retry"
            assert data["job_id"] == "test-doc-id"  # conftest.pyで設定したIDに合わせる


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
            
            response = await async_test_client.get(
                f"/backend/whisper/transcript/{file_hash}/original",
                headers={"Authorization": "Bearer test-token"}
            )
            
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
        
        # 既存のmock_gcp_servicesフィクスチャを使用するので、
        # 個別のモック化は不要。レスポンスを確認するだけ。
        response = await async_test_client.post(
            f"/backend/whisper/jobs/{file_hash}/edit",
            json=edit_request,
            headers={"Authorization": "Bearer test-token"}
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
                f"/backend/whisper/jobs/{file_hash}/speaker_config",
                json=speaker_config_request,
                headers={"Authorization": "Bearer test-token"}
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
            
            response = await async_test_client.get(
                f"/backend/whisper/jobs/{file_hash}/speaker_config",
                headers={"Authorization": "Bearer test-token"}
            )
            
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
            
            response = await async_test_client.get(
                f"/backend/whisper/jobs/{file_hash}/speaker_config",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data == {}  # 空のオブジェクトが返される


# エミュレータ使用例（オプション）
@pytest.mark.emulator
class TestWhisperJobOperationsWithEmulator:
    """GCPエミュレータを使用したジョブ操作テスト（使用例）"""
    
    @pytest.mark.asyncio
    async def test_job_storage_with_real_firestore_emulator(self, real_firestore_client, mock_auth_user):
        """実際のFirestoreエミュレータを使用したジョブ保存テスト"""
        
        # 実際のFirestoreクライアントを使用（エミュレータに接続）
        client = real_firestore_client
        
        # テストジョブデータ
        job_data = {
            "job_id": "emulator-api-test-123",
            "user_id": mock_auth_user["uid"],
            "user_email": mock_auth_user["email"],
            "filename": "emulator-api-test.wav",
            "gcs_bucket_name": "test-emulator-bucket",
            "file_hash": "emulator-api-hash",
            "status": "queued",
            "created_at": "2025-06-07T10:00:00Z"
        }
        
        # Firestoreにジョブを保存
        collection = client.collection('whisper_jobs')
        doc_ref = collection.document('emulator-api-doc')
        doc_ref.set(job_data)
        
        # データが正しく保存されたことを確認
        saved_doc = doc_ref.get()
        assert saved_doc.exists
        saved_data = saved_doc.to_dict()
        assert saved_data['job_id'] == job_data['job_id']
        assert saved_data['status'] == 'queued'
        
        # ステータス更新テスト
        doc_ref.update({"status": "processing"})
        updated_doc = doc_ref.get()
        assert updated_doc.to_dict()['status'] == 'processing'
        
        # ユーザークエリテスト
        user_jobs = list(collection.where('user_id', '==', mock_auth_user["uid"]).stream())
        assert len(user_jobs) >= 1
        assert any(job.to_dict()['job_id'] == job_data['job_id'] for job in user_jobs)
    
    @pytest.mark.asyncio
    async def test_file_storage_with_real_gcs_emulator(self, real_gcs_client):
        """実際のGCSエミュレータを使用したファイル操作テスト"""
        
        # 実際のGCSクライアントを使用（エミュレータに接続）
        client = real_gcs_client
        
        # バケットを作成
        bucket_name = 'test-emulator-api-bucket'
        try:
            bucket = client.create_bucket(bucket_name)
        except Exception:
            # バケットが既に存在する場合
            bucket = client.bucket(bucket_name)
        
        # 音声ファイルのアップロード
        audio_content = b"fake audio data for emulator API test"
        audio_blob = bucket.blob("whisper/emulator-api-hash.wav")
        audio_blob.upload_from_string(audio_content, content_type="audio/wav")
        
        # ファイルが正しくアップロードされたことを確認
        assert audio_blob.exists()
        assert audio_blob.content_type == "audio/wav"
        assert audio_blob.size == len(audio_content)
        
        # 署名付きURL生成テスト
        signed_url = audio_blob.generate_signed_url(expiration=3600)
        assert signed_url.startswith("http")
        assert bucket_name in signed_url
        
        # 文字起こし結果保存テスト
        transcript_data = [
            {"start": 0.0, "end": 1.0, "text": "エミュレータAPIテスト", "speaker": "SPEAKER_01"}
        ]
        result_blob = bucket.blob("emulator-api-hash/combine.json")
        result_blob.upload_from_string(
            json.dumps(transcript_data, ensure_ascii=False),
            content_type="application/json"
        )
        
        # 結果ファイルが正しく保存されたことを確認
        saved_transcript = json.loads(result_blob.download_as_text())
        assert len(saved_transcript) == 1
        assert saved_transcript[0]["text"] == "エミュレータAPIテスト"
