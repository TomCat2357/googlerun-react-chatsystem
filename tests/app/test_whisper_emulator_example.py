"""
Whisper API テスト（GCPエミュレータ使用例）
このファイルは、common_utils/gcp_emulator.pyを使用した
正しいテストの書き方を示す例として作成されています。
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, create_autospec

# GCPエミュレータのインポート
from common_utils.gcp_emulator import firestore_emulator_context, gcs_emulator_context

# Google Cloudクライアントのインポート（実際のクライアントを使用）
try:
    from google.cloud import firestore
    from google.cloud import storage
    REAL_GCP_AVAILABLE = True
except ImportError:
    REAL_GCP_AVAILABLE = False

from common_utils.class_types import WhisperFirestoreData


@pytest.mark.skipif(not REAL_GCP_AVAILABLE, reason="Real GCP libraries not available")
class TestWhisperWithGCPEmulator:
    """GCPエミュレータを使用したWhisper APIテスト"""
    
    @pytest.mark.asyncio
    async def test_firestore_job_storage_with_emulator(self):
        """Firestoreエミュレータを使用したジョブ保存テスト"""
        
        # Firestoreエミュレータを起動
        with firestore_emulator_context(
            host='localhost',
            port=8087,  # 他のテストと重複しないポート
            project_id='test-emulator-project'
        ) as emulator:
            
            # 実際のFirestoreクライアントを作成（エミュレータに接続）
            client = firestore.Client(project='test-emulator-project')
            
            # テストデータを準備
            job_data = {
                "job_id": "emulator-test-job-123",
                "user_id": "test-user-emulator",
                "user_email": "emulator@example.com",
                "filename": "emulator-test.wav",
                "gcs_bucket_name": "test-emulator-bucket",
                "audio_size": 44100,
                "audio_duration_ms": 1000,
                "file_hash": "emulator-test-hash",
                "language": "ja",
                "status": "queued",
                "num_speakers": 1,
                "min_speakers": 1,
                "max_speakers": 1,
                "description": "エミュレータテスト用音声"
            }
            
            # Firestoreにジョブを保存
            collection = client.collection('whisper_jobs')
            doc_ref = collection.document('emulator-test-doc')
            doc_ref.set(job_data)
            
            # データが正しく保存されたことを確認
            saved_doc = doc_ref.get()
            assert saved_doc.exists
            saved_data = saved_doc.to_dict()
            assert saved_data['job_id'] == job_data['job_id']
            assert saved_data['status'] == 'queued'
            
            # クエリテスト
            query = collection.where('user_id', '==', 'test-user-emulator')
            results = list(query.stream())
            assert len(results) == 1
            assert results[0].to_dict()['job_id'] == job_data['job_id']
    
    @pytest.mark.asyncio 
    async def test_gcs_file_operations_with_emulator(self):
        """GCSエミュレータを使用したファイル操作テスト"""
        
        # GCSエミュレータを起動
        with gcs_emulator_context(
            host='localhost',
            port=9007,  # 他のテストと重複しないポート
            project_id='test-emulator-gcs-project'
        ) as emulator:
            
            # 実際のGCSクライアントを作成（エミュレータに接続）
            client = storage.Client(project='test-emulator-gcs-project')
            
            # バケットを作成
            bucket_name = 'test-emulator-whisper-bucket'
            bucket = client.create_bucket(bucket_name)
            
            # テストファイルをアップロード
            test_content = b"fake audio data for emulator test"
            blob_name = "whisper/emulator-test-hash.wav"
            blob = bucket.blob(blob_name)
            blob.upload_from_string(test_content, content_type="audio/wav")
            
            # ファイルが正しくアップロードされたことを確認
            assert blob.exists()
            assert blob.content_type == "audio/wav"
            assert blob.size == len(test_content)
            
            # ファイルをダウンロード
            downloaded_content = blob.download_as_bytes()
            assert downloaded_content == test_content
            
            # 文字起こし結果ファイルの保存テスト
            transcript_data = [
                {"start": 0.0, "end": 1.0, "text": "エミュレータテスト音声", "speaker": "SPEAKER_01"}
            ]
            transcript_blob = bucket.blob("emulator-test-hash/combine.json")
            transcript_blob.upload_from_string(
                json.dumps(transcript_data, ensure_ascii=False),
                content_type="application/json"
            )
            
            # 文字起こし結果が正しく保存されたことを確認
            saved_transcript = json.loads(transcript_blob.download_as_text())
            assert len(saved_transcript) == 1
            assert saved_transcript[0]["text"] == "エミュレータテスト音声"
            assert saved_transcript[0]["speaker"] == "SPEAKER_01"
    
    @pytest.mark.asyncio
    async def test_combined_firestore_gcs_workflow_with_emulator(self):
        """FirestoreとGCSエミュレータを組み合わせたワークフローテスト"""
        
        # 両方のエミュレータを同時に起動
        with firestore_emulator_context(
            host='localhost',
            port=8088,
            project_id='test-combined-project'
        ) as fs_emulator, gcs_emulator_context(
            host='localhost', 
            port=9008,
            project_id='test-combined-project'
        ) as gcs_emulator:
            
            # クライアントを作成
            fs_client = firestore.Client(project='test-combined-project')
            gcs_client = storage.Client(project='test-combined-project')
            
            # GCSにファイルをアップロード
            bucket_name = 'test-combined-bucket'
            bucket = gcs_client.create_bucket(bucket_name)
            audio_blob = bucket.blob("combined-test-hash.wav")
            audio_blob.upload_from_string(b"combined test audio", content_type="audio/wav")
            
            # Firestoreにジョブを保存
            job_data = {
                "job_id": "combined-test-job",
                "user_id": "combined-test-user",
                "file_hash": "combined-test-hash",
                "gcs_bucket_name": bucket_name,
                "status": "processing",
                "filename": "combined-test.wav"
            }
            
            jobs_collection = fs_client.collection('whisper_jobs')
            job_doc = jobs_collection.document('combined-test-doc')
            job_doc.set(job_data)
            
            # 処理完了をシミュレート
            result_data = [
                {"start": 0.0, "end": 1.0, "text": "結合テスト音声", "speaker": "SPEAKER_01"}
            ]
            result_blob = bucket.blob("combined-test-hash/combine.json")
            result_blob.upload_from_string(
                json.dumps(result_data, ensure_ascii=False),
                content_type="application/json"
            )
            
            # ジョブステータスを更新
            job_doc.update({"status": "completed"})
            
            # 全体の整合性を確認
            updated_job = job_doc.get().to_dict()
            assert updated_job["status"] == "completed"
            
            saved_result = json.loads(result_blob.download_as_text())
            assert saved_result[0]["text"] == "結合テスト音声"
            
            # ユーザーのジョブ一覧を取得
            user_jobs = list(jobs_collection.where('user_id', '==', 'combined-test-user').stream())
            assert len(user_jobs) == 1
            assert user_jobs[0].to_dict()["status"] == "completed"


@pytest.mark.skipif(REAL_GCP_AVAILABLE, reason="Emulator tests should be skipped when real GCP is available")
class TestWhisperWithMockedEmulator:
    """GCPライブラリが利用できない場合のモックテスト"""
    
    @pytest.mark.asyncio
    async def test_firestore_operations_mocked(self):
        """Firestoreエミュレータが利用できない場合のモックテスト"""
        
        # エミュレータコンテキストをモック化
        with patch('common_utils.gcp_emulator.firestore_emulator_context') as mock_emulator_context:
            
            # モックエミュレータインスタンス
            mock_emulator = create_autospec(object)
            mock_emulator_context.return_value.__enter__.return_value = mock_emulator
            
            # モックFirestoreクライアント
            with patch('google.cloud.firestore.Client', autospec=True) as mock_client_class:
                mock_client = create_autospec(firestore.Client)
                mock_client_class.return_value = mock_client
                
                # モックコレクションとドキュメント
                mock_collection = create_autospec(firestore.CollectionReference)
                mock_document = create_autospec(firestore.DocumentReference)
                mock_client.collection.return_value = mock_collection
                mock_collection.document.return_value = mock_document
                
                # エミュレータを使用したテストをシミュレート
                with firestore_emulator_context(
                    port=8089,
                    project_id='test-mock-project'
                ) as emulator:
                    
                    client = firestore.Client(project='test-mock-project')
                    collection = client.collection('whisper_jobs')
                    doc_ref = collection.document('mock-test-doc')
                    
                    # モックの動作を確認
                    mock_client.collection.assert_called_with('whisper_jobs')
                    mock_collection.document.assert_called_with('mock-test-doc')
                    
                    # setメソッドが呼ばれることを確認
                    test_data = {"job_id": "mock-test", "status": "queued"}
                    doc_ref.set(test_data)
                    mock_document.set.assert_called_with(test_data)


# このファイルはemulator使用例のため、通常は無効化しておく
pytestmark = pytest.mark.skip(reason="Emulator example file - enable manually when testing emulator integration")