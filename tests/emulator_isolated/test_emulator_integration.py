"""
エミュレータ統合テスト（モック無し版）

このテストファイルは、実際のFirestore・GCSエミュレータを使用した包括的な統合テストを提供します。
モック化を一切行わず、実際のGCPライブラリとエミュレータで動作します。

ユニットテストの基本原則（SOS原則）を適用：
- S (Structured): 階層化されたテストクラス構造
- O (Organized): テスト設計根拠明記・パラメータテスト活用
- D (Self-documenting): AAA パターン・日本語テスト命名

テスト設計戦略：
- 実際のエミュレータ環境での統合テスト
- フィクスチャ干渉問題の完全回避
- pytest + 実際のGCPライブラリの組み合わせ
"""

import pytest
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

# GCPライブラリを直接インポート（モック無し）
from google.cloud import firestore, storage

# プロジェクト内モジュールのインポート
import sys
sys.path.append('/mnt/c/Users/gk3t-/OneDrive - 又村 友幸/working/googlerun-react-chatsystem')
from common_utils.logger import logger


@pytest.mark.emulator
class TestFirestoreEmulatorIntegration:
    """
    Firestoreエミュレータ統合テスト
    
    テスト設計の根拠：
    - 実際のエミュレータを使用した現実的な動作検証
    - CRUD操作の網羅的検証（Create, Read, Update, Delete）
    - 実際のWhisperジョブデータでの動作確認
    - トランザクション・クエリ機能の検証
    """
    
    class TestFirestoreCRUDOperations:
        """Firestore CRUD操作テストクラス（構造化）"""
        
        def test_create_whisper_job_document_正常なジョブデータで作成成功(self, emulator_environment):
            """正常なWhisperジョブデータでドキュメント作成が成功することを検証"""
            # Arrange（準備）
            env = emulator_environment
            job_id = f'emulator-create-job-{uuid.uuid4().hex[:8]}'
            job_data = {
                'jobId': job_id,
                'userId': 'emulator-user-001',
                'userEmail': 'emulator-test@example.com',
                'filename': 'emulator-test-audio.wav',
                'gcsBucketName': env.test_bucket.name,
                'audioSize': 2048000,
                'audioDurationMs': 45000,
                'fileHash': f'emulator-hash-{job_id}',
                'status': 'queued',
                'language': 'ja',
                'initialPrompt': 'エミュレータテスト用の音声認識です',
                'createdAt': env.SERVER_TIMESTAMP,
                'updatedAt': env.SERVER_TIMESTAMP,
                'numSpeakers': 2,
                'minSpeakers': 1,
                'maxSpeakers': 4,
                'tags': ['emulator', 'integration-test'],
                'description': 'エミュレータ統合テスト用ジョブ'
            }
            
            # Act（実行）
            doc_ref = env.test_collection.document(job_id)
            doc_ref.set(job_data)
            
            # Assert（検証）
            created_doc = doc_ref.get()
            assert created_doc.exists, "ドキュメントが作成されていません"
            
            stored_data = created_doc.to_dict()
            assert stored_data['jobId'] == job_id, "ジョブIDが正しく保存されていません"
            assert stored_data['status'] == 'queued', "ステータスが正しく保存されていません"
            assert stored_data['filename'] == 'emulator-test-audio.wav', "ファイル名が正しく保存されていません"
            assert stored_data['language'] == 'ja', "言語設定が正しく保存されていません"
            assert stored_data['numSpeakers'] == 2, "話者数が正しく保存されていません"
            assert 'emulator' in stored_data['tags'], "タグが正しく保存されていません"
            
            logger.info(f"✅ Firestore作成テスト成功: {job_id}")
        
        def test_read_whisper_job_document_存在するジョブで読み取り成功(self, emulator_environment):
            """存在するWhisperジョブデータの読み取りが成功することを検証"""
            # Arrange（準備）
            env = emulator_environment
            job_id = f'emulator-read-job-{uuid.uuid4().hex[:8]}'
            
            # テストデータを事前に作成
            test_data = {
                'jobId': job_id,
                'userId': 'emulator-read-user',
                'userEmail': 'read-test@example.com',
                'filename': 'read-test.wav',
                'gcsBucketName': env.test_bucket.name,
                'audioSize': 3072000,
                'audioDurationMs': 60000,
                'fileHash': f'read-hash-{job_id}',
                'status': 'processing',
                'language': 'en',
                'initialPrompt': 'English transcription test',
                'createdAt': env.SERVER_TIMESTAMP,
                'processStartedAt': env.SERVER_TIMESTAMP
            }
            
            doc_ref = env.test_collection.document(job_id)
            doc_ref.set(test_data)
            
            # Act（実行）
            retrieved_doc = doc_ref.get()
            
            # Assert（検証）
            assert retrieved_doc.exists, "ドキュメントが存在しません"
            retrieved_data = retrieved_doc.to_dict()
            assert retrieved_data['jobId'] == job_id, "読み取ったジョブIDが一致しません"
            assert retrieved_data['status'] == 'processing', "読み取ったステータスが一致しません"
            assert retrieved_data['audioSize'] == 3072000, "読み取った音声サイズが一致しません"
            assert retrieved_data['language'] == 'en', "読み取った言語設定が一致しません"
            
            logger.info(f"✅ Firestore読み取りテスト成功: {job_id}")
        
        def test_update_whisper_job_status_ステータス更新で正常動作(self, emulator_environment):
            """Whisperジョブのステータス更新が正常に動作することを検証"""
            # Arrange（準備）
            env = emulator_environment
            job_id = f'emulator-update-job-{uuid.uuid4().hex[:8]}'
            
            # 初期データの作成
            initial_data = {
                'jobId': job_id,
                'userId': 'emulator-update-user',
                'userEmail': 'update-test@example.com',
                'filename': 'update-test.wav',
                'gcsBucketName': env.test_bucket.name,
                'audioSize': 1536000,
                'audioDurationMs': 30000,
                'fileHash': f'update-hash-{job_id}',
                'status': 'queued',
                'language': 'ja',
                'createdAt': env.SERVER_TIMESTAMP
            }
            
            doc_ref = env.test_collection.document(job_id)
            doc_ref.set(initial_data)
            
            # Act（実行）
            update_data = {
                'status': 'completed',
                'updatedAt': env.SERVER_TIMESTAMP,
                'processEndedAt': env.SERVER_TIMESTAMP,
                'transcriptionResult': {
                    'segments': [
                        {'start': 0.0, 'end': 2.5, 'text': '更新テストです', 'speaker': 'SPEAKER_01'},
                        {'start': 2.5, 'end': 5.0, 'text': '正常に完了しました', 'speaker': 'SPEAKER_01'}
                    ],
                    'totalDuration': 5.0,
                    'speakerCount': 1
                }
            }
            doc_ref.update(update_data)
            
            # Assert（検証）
            updated_doc = doc_ref.get()
            updated_data = updated_doc.to_dict()
            assert updated_data['status'] == 'completed', "ステータスが正しく更新されていません"
            assert updated_data['jobId'] == job_id, "他のフィールドが保持されていません"
            assert 'processEndedAt' in updated_data, "プロセス終了時刻が設定されていません"
            assert 'transcriptionResult' in updated_data, "文字起こし結果が保存されていません"
            assert len(updated_data['transcriptionResult']['segments']) == 2, "セグメント数が正しくありません"
            
            logger.info(f"✅ Firestoreステータス更新テスト成功: {job_id}")
        
        def test_delete_whisper_job_document_削除操作で正常動作(self, emulator_environment):
            """Whisperジョブドキュメントの削除が正常に動作することを検証"""
            # Arrange（準備）
            env = emulator_environment
            job_id = f'emulator-delete-job-{uuid.uuid4().hex[:8]}'
            
            # テストデータの作成
            test_data = {
                'jobId': job_id,
                'userId': 'emulator-delete-user',
                'userEmail': 'delete-test@example.com',
                'filename': 'delete-test.wav',
                'gcsBucketName': env.test_bucket.name,
                'audioSize': 512000,
                'audioDurationMs': 15000,
                'fileHash': f'delete-hash-{job_id}',
                'status': 'failed',
                'language': 'ja',
                'errorMessage': '削除テスト用の失敗ジョブです'
            }
            
            doc_ref = env.test_collection.document(job_id)
            doc_ref.set(test_data)
            
            # 作成確認
            assert doc_ref.get().exists, "テストデータが作成されていません"
            
            # Act（実行）
            doc_ref.delete()
            
            # Assert（検証）
            deleted_doc = doc_ref.get()
            assert not deleted_doc.exists, "ドキュメントが削除されていません"
            
            logger.info(f"✅ Firestore削除テスト成功: {job_id}")
    
    class TestFirestoreQueries:
        """Firestoreクエリテストクラス（整理されたテスト設計）"""
        
        @pytest.mark.parametrize(
            ["status", "expected_count"],
            [
                ("queued", 3),
                ("processing", 2),
                ("completed", 2),
                ("failed", 1),
            ],
            ids=[
                "キューステータス_3件期待",
                "処理中ステータス_2件期待",
                "完了ステータス_2件期待",
                "失敗ステータス_1件期待",
            ],
        )
        def test_query_jobs_by_status_各ステータスで正しい件数取得(
            self, emulator_environment, status, expected_count
        ):
            """各ステータスでWhisperジョブクエリが正しい件数を返すことを検証"""
            # Arrange（準備）
            env = emulator_environment
            base_id = uuid.uuid4().hex[:6]
            
            # テストデータセットの投入
            test_jobs = [
                # queued jobs (3件)
                {'jobId': f'emulator-queued-1-{base_id}', 'status': 'queued', 'userId': 'user1'},
                {'jobId': f'emulator-queued-2-{base_id}', 'status': 'queued', 'userId': 'user2'},
                {'jobId': f'emulator-queued-3-{base_id}', 'status': 'queued', 'userId': 'user3'},
                # processing jobs (2件)
                {'jobId': f'emulator-processing-1-{base_id}', 'status': 'processing', 'userId': 'user4'},
                {'jobId': f'emulator-processing-2-{base_id}', 'status': 'processing', 'userId': 'user5'},
                # completed jobs (2件)
                {'jobId': f'emulator-completed-1-{base_id}', 'status': 'completed', 'userId': 'user6'},
                {'jobId': f'emulator-completed-2-{base_id}', 'status': 'completed', 'userId': 'user7'},
                # failed job (1件)
                {'jobId': f'emulator-failed-1-{base_id}', 'status': 'failed', 'userId': 'user8'},
            ]
            
            # テストデータ投入
            for job in test_jobs:
                doc_ref = env.test_collection.document(job['jobId'])
                doc_ref.set({
                    **job,
                    'userEmail': f"{job['userId']}@emulator.example.com",
                    'filename': f"{job['jobId']}.wav",
                    'gcsBucketName': env.test_bucket.name,
                    'audioSize': 1000000,
                    'audioDurationMs': 30000,
                    'fileHash': f"emulator-hash-{job['jobId']}",
                    'language': 'ja',
                    'createdAt': env.SERVER_TIMESTAMP
                })
            
            # Act（実行）
            query_results = env.test_collection.where('status', '==', status).stream()
            actual_count = len(list(query_results))
            
            # Assert（検証）
            assert actual_count == expected_count, f"ステータス '{status}' の件数が期待値と異なります: 実際={actual_count}, 期待={expected_count}"
            
            logger.info(f"✅ Firestoreクエリテスト成功: ステータス={status}, 件数={actual_count}")


@pytest.mark.emulator
class TestGCSEmulatorIntegration:
    """
    GCSエミュレータ統合テスト
    
    テスト設計の根拠：
    - ファイルアップロード・ダウンロード・削除の網羅的検証
    - 実際の音声ファイル処理ワークフローでの動作確認
    - メタデータ・フォルダー構造の検証
    """
    
    class TestGCSFileOperations:
        """GCS ファイル操作テストクラス（自己文書化）"""
        
        def test_upload_audio_file_音声ファイルアップロードで正常動作(self, emulator_environment):
            """音声ファイルのアップロードが正常に動作することを検証"""
            # Arrange（準備）
            env = emulator_environment
            file_path = f'emulator/audio/test-audio-{uuid.uuid4().hex[:8]}.wav'
            
            # 模擬音声データ（WAVヘッダー風）
            audio_content = b'RIFF' + (1000).to_bytes(4, 'little') + b'WAVE' + b'fmt ' + b'\x00' * 1000
            
            # Act（実行）
            blob = env.test_bucket.blob(file_path)
            blob.upload_from_string(audio_content, content_type='audio/wav')
            
            # Assert（検証）
            assert blob.exists(), "アップロードされたファイルが存在しません"
            assert blob.size == len(audio_content), "ファイルサイズが期待値と異なります"
            assert blob.content_type == 'audio/wav', "コンテンツタイプが正しく設定されていません"
            
            # ダウンロード検証
            downloaded_content = blob.download_as_bytes()
            assert downloaded_content == audio_content, "ダウンロードしたコンテンツが元データと一致しません"
            
            logger.info(f"✅ GCS音声ファイルアップロードテスト成功: {file_path}")
        
        def test_upload_transcription_result_文字起こし結果アップロードで正常動作(self, emulator_environment):
            """文字起こし結果のアップロードが正常に動作することを検証"""
            # Arrange（準備）
            env = emulator_environment
            job_id = f'emulator-transcription-{uuid.uuid4().hex[:8]}'
            result_path = f'emulator/results/{job_id}/transcription.json'
            
            transcription_data = {
                'jobId': job_id,
                'segments': [
                    {'start': 0.0, 'end': 2.3, 'text': 'エミュレータテストです', 'speaker': 'SPEAKER_01'},
                    {'start': 2.3, 'end': 5.8, 'text': '文字起こし結果の保存をテストしています', 'speaker': 'SPEAKER_01'},
                    {'start': 5.8, 'end': 8.2, 'text': '正常に動作することを確認します', 'speaker': 'SPEAKER_02'},
                ],
                'language': 'ja',
                'duration': 8.2,
                'processingTime': 2.1,
                'speakerCount': 2,
                'confidence': 0.95,
                'model': 'whisper-large-v3',
                'processingTimestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Act（実行）
            blob = env.test_bucket.blob(result_path)
            blob.upload_from_string(
                json.dumps(transcription_data, ensure_ascii=False, indent=2),
                content_type='application/json'
            )
            
            # Assert（検証）
            assert blob.exists(), "文字起こし結果ファイルが存在しません"
            
            # ダウンロード・パース検証
            downloaded_json = json.loads(blob.download_as_text())
            assert downloaded_json['jobId'] == job_id, "ジョブIDが正しく保存されていません"
            assert len(downloaded_json['segments']) == 3, "セグメント数が期待値と異なります"
            assert downloaded_json['segments'][0]['text'] == 'エミュレータテストです', "最初のセグメントテキストが一致しません"
            assert downloaded_json['speakerCount'] == 2, "話者数が正しく保存されていません"
            assert downloaded_json['confidence'] == 0.95, "信頼度が正しく保存されていません"
            
            logger.info(f"✅ GCS文字起こし結果アップロードテスト成功: {result_path}")


@pytest.mark.emulator
class TestWhisperEmulatorWorkflow:
    """
    Whisper統合ワークフローテスト
    
    実際のWhisper処理フローでFirestore・GCSエミュレータの統合動作を検証
    """
    
    def test_complete_whisper_workflow_完全なワークフローで正常動作(self, emulator_environment):
        """完全なWhisperワークフローが正常に動作することを検証"""
        # Arrange（準備）
        env = emulator_environment
        job_id = f'emulator-integration-{uuid.uuid4().hex[:8]}'
        user_id = f'emulator-user-{uuid.uuid4().hex[:8]}'
        original_filename = 'emulator-meeting-recording.wav'
        
        # 1. 音声ファイルアップロード（GCS）
        audio_content = b'RIFF' + (5000).to_bytes(4, 'little') + b'WAVE' + b'fmt ' + b'\x00' * 5000
        audio_path = f'emulator/audio/{job_id}/original.wav'
        
        audio_blob = env.test_bucket.blob(audio_path)
        audio_blob.metadata = {
            'originalFileName': original_filename,
            'userId': user_id,
            'jobId': job_id,
            'uploadTimestamp': datetime.now(timezone.utc).isoformat(),
            'fileVersion': '1.0'
        }
        audio_blob.upload_from_string(audio_content, content_type='audio/wav')
        
        # 2. ジョブデータ作成（Firestore）
        job_data = {
            'jobId': job_id,
            'userId': user_id,
            'userEmail': f'{user_id}@emulator.example.com',
            'filename': original_filename,
            'gcsBucketName': env.test_bucket.name,
            'audioSize': len(audio_content),
            'audioDurationMs': 180000,  # 3分
            'fileHash': f'emulator-sha256-{job_id}',
            'status': 'queued',
            'language': 'ja',
            'initialPrompt': 'エミュレータテスト用の会議録音です',
            'numSpeakers': 3,
            'minSpeakers': 1,
            'maxSpeakers': 5,
            'tags': ['emulator', 'integration', 'meeting'],
            'description': 'エミュレータ統合テスト用完全ワークフロー',
            'createdAt': env.SERVER_TIMESTAMP,
            'updatedAt': env.SERVER_TIMESTAMP
        }
        
        job_ref = env.test_collection.document(job_id)
        job_ref.set(job_data)
        
        # Act & Assert（実行と検証）
        # 3. ジョブステータス更新 → 処理中
        job_ref.update({
            'status': 'processing',
            'processStartedAt': env.SERVER_TIMESTAMP,
            'updatedAt': env.SERVER_TIMESTAMP,
            'processingNode': 'emulator-node-001'
        })
        
        processing_doc = job_ref.get()
        processing_data = processing_doc.to_dict()
        assert processing_data['status'] == 'processing', "ステータスが処理中に更新されていません"
        assert 'processStartedAt' in processing_data, "処理開始時刻が設定されていません"
        
        # 4. 文字起こし結果保存（GCS）
        transcription_result = {
            'jobId': job_id,
            'segments': [
                {'start': 0.0, 'end': 4.2, 'text': 'エミュレータテスト会議を開始します', 'speaker': 'SPEAKER_01', 'confidence': 0.98},
                {'start': 4.2, 'end': 8.8, 'text': '今日の議題は統合テストの結果について', 'speaker': 'SPEAKER_02', 'confidence': 0.95},
                {'start': 8.8, 'end': 12.5, 'text': 'エミュレータテストが正常に動作していることを確認', 'speaker': 'SPEAKER_01', 'confidence': 0.97},
            ],
            'language': 'ja',
            'duration': 12.5,
            'processingTime': 3.2,
            'speakerCount': 2,
            'confidence': 0.97,
            'model': 'whisper-large-v3',
            'processingTimestamp': datetime.now(timezone.utc).isoformat()
        }
        
        result_path = f'emulator/results/{job_id}/transcription.json'
        result_blob = env.test_bucket.blob(result_path)
        result_blob.upload_from_string(
            json.dumps(transcription_result, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        
        # 5. ジョブ完了更新（Firestore）
        job_ref.update({
            'status': 'completed',
            'processEndedAt': env.SERVER_TIMESTAMP,
            'updatedAt': env.SERVER_TIMESTAMP,
            'completionData': {
                'transcriptionPath': result_path,
                'totalDuration': transcription_result['duration'],
                'speakerCount': transcription_result['speakerCount'],
                'confidence': transcription_result['confidence'],
                'processingTime': transcription_result['processingTime']
            }
        })
        
        # 6. 最終検証（統合性確認）
        completed_doc = job_ref.get()
        completed_data = completed_doc.to_dict()
        assert completed_data['status'] == 'completed', "最終ステータスが完了になっていません"
        assert completed_data['jobId'] == job_id, "ジョブIDが保持されていません"
        assert 'processEndedAt' in completed_data, "処理終了時刻が設定されていません"
        
        # GCSファイル存在確認
        assert audio_blob.exists(), "音声ファイルが存在しません"
        assert result_blob.exists(), "文字起こし結果ファイルが存在しません"
        
        # 結果ファイル内容検証
        downloaded_result = json.loads(result_blob.download_as_text())
        assert downloaded_result['jobId'] == job_id, "結果ファイルのジョブIDが一致しません"
        assert len(downloaded_result['segments']) == 3, "セグメント数が期待値と異なります"
        assert downloaded_result['speakerCount'] == 2, "話者数が期待値と異なります"
        
        logger.info(f'✅ エミュレータ統合ワークフローテスト完了: {job_id}')


if __name__ == '__main__':
    """テストファイル単体実行時の処理"""
    print("エミュレータ統合テストスイート（モック無し版）")
    print("実行前にエミュレータが起動していることを確認してください:")
    print("python tests/app/gcp_emulator_run.py")
    print()
    print("テスト実行コマンド:")
    print("pytest tests/emulator_isolated/test_emulator_integration.py -v -m emulator")