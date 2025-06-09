"""
GCPエミュレータ データ操作テスト

Firestore・GCSエミュレータでの実際のデータ操作（CRUD）を検証
"""

import pytest
import json
import os
from datetime import datetime
from google.cloud import firestore, storage


@pytest.mark.skipif(
    not os.environ.get('FIRESTORE_EMULATOR_HOST'), 
    reason="Firestoreエミュレータが起動していません"
)
class TestFirestoreDataOperations:
    """Firestoreデータ操作テスト"""
    
    def setup_method(self):
        """各テストメソッド前の初期化"""
        self.db = firestore.Client(project='test-emulator-project')
    
    def test_firestore_crud_operations_完全なCRUD操作で正常動作(self):
        """Firestoreの完全なCRUD操作が正常に動作することを検証"""
        # Create - データ作成
        job_data = {
            'jobId': 'test-crud-001',
            'userId': 'user-crud',
            'userEmail': 'crud@example.com',
            'filename': 'crud-test.wav',
            'status': 'queued',
            'language': 'ja',
            'createdAt': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = self.db.collection('whisper_jobs').document('test-crud-001')
        doc_ref.set(job_data)
        
        # Read - データ読み取り
        doc = doc_ref.get()
        assert doc.exists
        data = doc.to_dict()
        assert data['jobId'] == 'test-crud-001'
        assert data['status'] == 'queued'
        
        # Update - データ更新
        doc_ref.update({
            'status': 'completed',
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        updated_doc = doc_ref.get()
        updated_data = updated_doc.to_dict()
        assert updated_data['status'] == 'completed'
        assert updated_data['jobId'] == 'test-crud-001'  # 他フィールド保持確認
        
        # Delete - データ削除
        doc_ref.delete()
        deleted_doc = doc_ref.get()
        assert not deleted_doc.exists
        
        print("✅ Firestore CRUD操作テスト完了")
    
    def test_firestore_query_operations_クエリ操作で正常動作(self):
        """Firestoreのクエリ操作が正常に動作することを検証"""
        # テストデータ作成
        test_jobs = [
            {'jobId': 'query-job-1', 'status': 'queued', 'userId': 'user1'},
            {'jobId': 'query-job-2', 'status': 'processing', 'userId': 'user1'},
            {'jobId': 'query-job-3', 'status': 'completed', 'userId': 'user2'},
        ]
        
        collection = self.db.collection('whisper_jobs')
        for job in test_jobs:
            collection.document(job['jobId']).set(job)
        
        # ステータス別クエリ
        queued_jobs = list(collection.where('status', '==', 'queued').stream())
        assert len(queued_jobs) == 1
        assert queued_jobs[0].to_dict()['jobId'] == 'query-job-1'
        
        # ユーザー別クエリ
        user1_jobs = list(collection.where('userId', '==', 'user1').stream())
        assert len(user1_jobs) == 2
        
        # クリーンアップ
        for job in test_jobs:
            collection.document(job['jobId']).delete()
        
        print("✅ Firestore クエリ操作テスト完了")


@pytest.mark.skipif(
    not os.environ.get('STORAGE_EMULATOR_HOST'), 
    reason="GCSエミュレータが起動していません"
)
class TestGCSDataOperations:
    """GCSデータ操作テスト"""
    
    def setup_method(self):
        """各テストメソッド前の初期化"""
        self.client = storage.Client(project='test-emulator-project')
        self.bucket_name = 'test-data-operations'
        
        # バケット作成
        try:
            self.bucket = self.client.bucket(self.bucket_name)
            self.bucket.create()
        except Exception:
            self.bucket = self.client.bucket(self.bucket_name)
    
    def test_gcs_file_operations_ファイル操作で正常動作(self):
        """GCSのファイル操作が正常に動作することを検証"""
        # テキストファイルアップロード
        text_content = "こんにちは、GCSエミュレータテスト！\\n日本語もOKです。"
        text_blob = self.bucket.blob('test/sample.txt')
        text_blob.upload_from_string(text_content, content_type='text/plain; charset=utf-8')
        
        # アップロード確認
        assert text_blob.exists()
        
        # ダウンロード・検証
        downloaded = text_blob.download_as_text()
        assert downloaded == text_content
        
        # JSONファイルアップロード
        json_data = {
            'test': True,
            'message': 'GCSエミュレータJSONテスト',
            'timestamp': datetime.now().isoformat()
        }
        json_blob = self.bucket.blob('test/data.json')
        json_blob.upload_from_string(
            json.dumps(json_data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        
        # JSONダウンロード・検証
        downloaded_json = json.loads(json_blob.download_as_text())
        assert downloaded_json['test'] is True
        assert downloaded_json['message'] == 'GCSエミュレータJSONテスト'
        
        # ファイル一覧確認
        blobs = list(self.bucket.list_blobs(prefix='test/'))
        assert len(blobs) == 2
        
        # ファイル削除
        text_blob.delete()
        json_blob.delete()
        
        # 削除確認
        assert not text_blob.exists()
        assert not json_blob.exists()
        
        print("✅ GCS ファイル操作テスト完了")
    
    def test_gcs_metadata_operations_メタデータ操作で正常動作(self):
        """GCSのメタデータ操作が正常に動作することを検証"""
        # メタデータ付きファイルアップロード
        file_content = "メタデータテスト用ファイル"
        metadata = {
            'author': 'Test User',
            'purpose': 'Emulator Testing',
            'version': '1.0'
        }
        
        blob = self.bucket.blob('metadata/test-file.txt')
        blob.metadata = metadata
        blob.upload_from_string(file_content)
        
        # メタデータ読み取り・検証
        blob.reload()
        assert blob.metadata is not None
        assert blob.metadata['author'] == 'Test User'
        assert blob.metadata['purpose'] == 'Emulator Testing'
        
        # メタデータ更新
        blob.metadata['version'] = '2.0'
        blob.metadata['updated'] = datetime.now().isoformat()
        blob.patch()
        
        # 更新確認
        blob.reload()
        assert blob.metadata['version'] == '2.0'
        assert 'updated' in blob.metadata
        
        # クリーンアップ
        blob.delete()
        
        print("✅ GCS メタデータ操作テスト完了")


@pytest.mark.skipif(
    not (os.environ.get('FIRESTORE_EMULATOR_HOST') and os.environ.get('STORAGE_EMULATOR_HOST')),
    reason="Firestore・GCSエミュレータの両方が必要です"
)
class TestIntegratedWorkflow:
    """統合ワークフローテスト"""
    
    def setup_method(self):
        """各テストメソッド前の初期化"""
        self.db = firestore.Client(project='test-emulator-project')
        self.storage_client = storage.Client(project='test-emulator-project')
        self.bucket_name = 'test-integrated-workflow'
        
        # バケット作成
        try:
            self.bucket = self.storage_client.bucket(self.bucket_name)
            self.bucket.create()
        except Exception:
            self.bucket = self.storage_client.bucket(self.bucket_name)
    
    def test_whisper_workflow_simulation_Whisperワークフロー模擬で正常動作(self):
        """Whisperワークフローの模擬実行が正常に動作することを検証"""
        job_id = 'workflow-test-001'
        
        # 1. 音声ファイルアップロード（GCS）
        audio_content = b'FAKE_AUDIO_DATA_FOR_TESTING'
        audio_path = f'whisper/audio/{job_id}.wav'
        audio_blob = self.bucket.blob(audio_path)
        audio_blob.metadata = {
            'jobId': job_id,
            'originalName': 'user-recording.wav'
        }
        audio_blob.upload_from_string(audio_content, content_type='audio/wav')
        
        # 2. ジョブデータ作成（Firestore）
        job_data = {
            'jobId': job_id,
            'userId': 'workflow-user',
            'filename': 'user-recording.wav',
            'status': 'queued',
            'gcsBucketName': self.bucket_name,
            'audioPath': audio_path,
            'createdAt': firestore.SERVER_TIMESTAMP
        }
        job_ref = self.db.collection('whisper_jobs').document(job_id)
        job_ref.set(job_data)
        
        # 3. 処理開始（ステータス更新）
        job_ref.update({
            'status': 'processing',
            'processStartedAt': firestore.SERVER_TIMESTAMP
        })
        
        # 4. 文字起こし結果保存（GCS）
        transcription_data = {
            'jobId': job_id,
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': 'テスト音声です', 'speaker': 'SPEAKER_01'}
            ],
            'language': 'ja'
        }
        result_path = f'whisper/results/{job_id}.json'
        result_blob = self.bucket.blob(result_path)
        result_blob.upload_from_string(
            json.dumps(transcription_data, ensure_ascii=False),
            content_type='application/json'
        )
        
        # 5. 処理完了（ステータス更新）
        job_ref.update({
            'status': 'completed',
            'resultPath': result_path,
            'processEndedAt': firestore.SERVER_TIMESTAMP
        })
        
        # 検証
        # Firestoreデータ確認
        final_job = job_ref.get()
        final_data = final_job.to_dict()
        assert final_data['status'] == 'completed'
        assert final_data['resultPath'] == result_path
        
        # GCSファイル確認
        assert audio_blob.exists()
        assert result_blob.exists()
        
        # 結果ファイル内容確認
        result_content = json.loads(result_blob.download_as_text())
        assert result_content['jobId'] == job_id
        assert len(result_content['segments']) == 1
        
        # クリーンアップ
        job_ref.delete()
        audio_blob.delete()
        result_blob.delete()
        
        print(f"✅ 統合ワークフロー模擬テスト完了: {job_id}")


if __name__ == "__main__":
    # 直接実行用のテスト
    print("=== GCPエミュレータ データ操作テスト ===")
    
    # 環境変数確認
    firestore_host = os.environ.get('FIRESTORE_EMULATOR_HOST')
    gcs_host = os.environ.get('STORAGE_EMULATOR_HOST')
    
    print(f"Firestore: {firestore_host}")
    print(f"GCS: {gcs_host}")
    
    if firestore_host and gcs_host:
        print("✅ 両エミュレータが利用可能です")
    else:
        print("❌ エミュレータが起動していません")