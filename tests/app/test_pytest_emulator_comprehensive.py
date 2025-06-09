"""
Pytest包括的エミュレータテストスイート

このテストファイルは、Firestore・GCSエミュレータの包括的な機能テストを提供し、
実際のWhisperワークフローでの統合動作をpytestフレームワークで検証します。

ユニットテストの基本原則（SOS原則）を適用：
- S (Structured): 階層化されたテストクラス構造
- O (Organized): テスト設計根拠明記・パラメータテスト活用
- D (Self-documenting): AAA パターン・日本語テスト命名

テスト設計戦略：
- create_autospec + side_effect パターンの適用
- 実際のエミュレータ環境での統合テスト
- フィクスチャ干渉問題の解決
- 前回の成功パターンの踏襲と改良
"""

import pytest
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import create_autospec, patch, MagicMock

# プロジェクト内モジュールのインポート
from common_utils.class_types import WhisperJobData
from common_utils.logger import logger

# エミュレータ専用設定をインポート
pytest_plugins = ["tests.app.conftest_emulator"]


@pytest.mark.emulator
class TestPytestFirestoreEmulatorIntegration:
    """
    Pytest版Firestoreエミュレータ統合テスト
    
    テスト設計の根拠：
    - 実際のエミュレータを使用した現実的な動作検証
    - CRUD操作の網羅的検証（Create, Read, Update, Delete）
    - 実際のWhisperジョブデータでの動作確認
    - トランザクション・クエリ機能の検証
    - 同時実行・競合状態のテスト
    """
    
    class TestFirestoreCRUDOperations:
        """Firestore CRUD操作テストクラス（構造化）"""
        
        def test_create_whisper_job_document_正常なジョブデータで作成成功(self, comprehensive_emulator_setup):
            """正常なWhisperジョブデータでドキュメント作成が成功することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            job_id = f'pytest-create-job-{uuid.uuid4().hex[:8]}'
            job_data = {
                'jobId': job_id,
                'userId': 'pytest-user-001',
                'userEmail': 'pytest-test@example.com',
                'filename': 'pytest-test-audio.wav',
                'gcsBucketName': env.test_bucket.name,
                'audioSize': 2048000,
                'audioDurationMs': 45000,
                'fileHash': f'pytest-hash-{job_id}',
                'status': 'queued',
                'language': 'ja',
                'initialPrompt': 'Pytestテスト用の音声認識です',
                'createdAt': env.SERVER_TIMESTAMP,
                'updatedAt': env.SERVER_TIMESTAMP,
                'numSpeakers': 2,
                'minSpeakers': 1,
                'maxSpeakers': 4,
                'tags': ['pytest', 'integration-test'],
                'description': 'Pytest統合テスト用ジョブ'
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
            assert stored_data['filename'] == 'pytest-test-audio.wav', "ファイル名が正しく保存されていません"
            assert stored_data['language'] == 'ja', "言語設定が正しく保存されていません"
            assert stored_data['numSpeakers'] == 2, "話者数が正しく保存されていません"
            assert 'pytest' in stored_data['tags'], "タグが正しく保存されていません"
            
            logger.info(f"✅ Firestore作成テスト成功: {job_id}")
        
        def test_read_whisper_job_document_存在するジョブで読み取り成功(self, comprehensive_emulator_setup):
            """存在するWhisperジョブデータの読み取りが成功することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            job_id = f'pytest-read-job-{uuid.uuid4().hex[:8]}'
            
            # テストデータを事前に作成
            test_data = {
                'jobId': job_id,
                'userId': 'pytest-read-user',
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
        
        def test_update_whisper_job_status_ステータス更新で正常動作(self, comprehensive_emulator_setup):
            """Whisperジョブのステータス更新が正常に動作することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            job_id = f'pytest-update-job-{uuid.uuid4().hex[:8]}'
            
            # 初期データの作成
            initial_data = {
                'jobId': job_id,
                'userId': 'pytest-update-user',
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
        
        def test_delete_whisper_job_document_削除操作で正常動作(self, comprehensive_emulator_setup):
            """Whisperジョブドキュメントの削除が正常に動作することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            job_id = f'pytest-delete-job-{uuid.uuid4().hex[:8]}'
            
            # テストデータの作成
            test_data = {
                'jobId': job_id,
                'userId': 'pytest-delete-user',
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
            self, comprehensive_emulator_setup, status, expected_count
        ):
            """各ステータスでWhisperジョブクエリが正しい件数を返すことを検証
            
            テスト設計の根拠：
            - 同値分割：各ステータス値でのクエリ結果検証
            - データ量境界：少数データでのクエリ性能確認
            - 実際の使用パターン：管理画面でのステータス別表示機能
            """
            # Arrange（準備）
            env = comprehensive_emulator_setup
            base_id = uuid.uuid4().hex[:6]
            
            # テストデータセットの投入
            test_jobs = [
                # queued jobs (3件)
                {'jobId': f'pytest-queued-1-{base_id}', 'status': 'queued', 'userId': 'user1'},
                {'jobId': f'pytest-queued-2-{base_id}', 'status': 'queued', 'userId': 'user2'},
                {'jobId': f'pytest-queued-3-{base_id}', 'status': 'queued', 'userId': 'user3'},
                # processing jobs (2件)
                {'jobId': f'pytest-processing-1-{base_id}', 'status': 'processing', 'userId': 'user4'},
                {'jobId': f'pytest-processing-2-{base_id}', 'status': 'processing', 'userId': 'user5'},
                # completed jobs (2件)
                {'jobId': f'pytest-completed-1-{base_id}', 'status': 'completed', 'userId': 'user6'},
                {'jobId': f'pytest-completed-2-{base_id}', 'status': 'completed', 'userId': 'user7'},
                # failed job (1件)
                {'jobId': f'pytest-failed-1-{base_id}', 'status': 'failed', 'userId': 'user8'},
            ]
            
            # テストデータ投入
            for job in test_jobs:
                doc_ref = env.test_collection.document(job['jobId'])
                doc_ref.set({
                    **job,
                    'userEmail': f"{job['userId']}@pytest.example.com",
                    'filename': f"{job['jobId']}.wav",
                    'gcsBucketName': env.test_bucket.name,
                    'audioSize': 1000000,
                    'audioDurationMs': 30000,
                    'fileHash': f"pytest-hash-{job['jobId']}",
                    'language': 'ja',
                    'createdAt': env.SERVER_TIMESTAMP
                })
            
            # Act（実行）
            query_results = env.test_collection.where('status', '==', status).stream()
            actual_count = len(list(query_results))
            
            # Assert（検証）
            assert actual_count == expected_count, f"ステータス '{status}' の件数が期待値と異なります: 実際={actual_count}, 期待={expected_count}"
            
            logger.info(f"✅ Firestoreクエリテスト成功: ステータス={status}, 件数={actual_count}")
        
        def test_query_jobs_by_user_id_特定ユーザーのジョブ一覧取得(self, comprehensive_emulator_setup):
            """特定ユーザーのWhisperジョブ一覧取得が正常に動作することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            target_user = f'pytest-target-user-{uuid.uuid4().hex[:8]}'
            other_user = f'pytest-other-user-{uuid.uuid4().hex[:8]}'
            base_id = uuid.uuid4().hex[:6]
            
            user_jobs = [
                # ターゲットユーザーのジョブ (3件)
                {'jobId': f'pytest-user-job-1-{base_id}', 'userId': target_user, 'status': 'completed'},
                {'jobId': f'pytest-user-job-2-{base_id}', 'userId': target_user, 'status': 'queued'},
                {'jobId': f'pytest-user-job-3-{base_id}', 'userId': target_user, 'status': 'failed'},
                # 他のユーザーのジョブ (1件)
                {'jobId': f'pytest-other-job-1-{base_id}', 'userId': other_user, 'status': 'completed'},
            ]
            
            # テストデータ投入
            for job in user_jobs:
                doc_ref = env.test_collection.document(job['jobId'])
                doc_ref.set({
                    **job,
                    'userEmail': f"{job['userId']}@pytest.example.com",
                    'filename': f"{job['jobId']}.wav",
                    'gcsBucketName': env.test_bucket.name,
                    'audioSize': 1000000,
                    'audioDurationMs': 30000,
                    'fileHash': f"pytest-hash-{job['jobId']}",
                    'language': 'ja',
                    'createdAt': env.SERVER_TIMESTAMP
                })
            
            # Act（実行）
            user_query_results = env.test_collection.where('userId', '==', target_user).stream()
            user_jobs_list = list(user_query_results)
            
            # Assert（検証）
            assert len(user_jobs_list) == 3, f"ユーザー {target_user} のジョブ数が期待値と異なります"
            for job_doc in user_jobs_list:
                job_data = job_doc.to_dict()
                assert job_data['userId'] == target_user, "取得したジョブのユーザーIDが一致しません"
                assert job_doc.id.startswith('pytest-user-job-'), "取得したジョブIDが期待パターンと一致しません"
            
            logger.info(f"✅ Firestoreユーザー別クエリテスト成功: ユーザー={target_user}, 件数={len(user_jobs_list)}")


@pytest.mark.emulator
class TestPytestGCSEmulatorIntegration:
    """
    Pytest版GCSエミュレータ統合テスト
    
    テスト設計の根拠：
    - ファイルアップロード・ダウンロード・削除の網羅的検証
    - 実際の音声ファイル処理ワークフローでの動作確認
    - メタデータ・フォルダー構造の検証
    - ファイル権限・アクセス制御の確認
    - 大容量ファイル処理のテスト
    """
    
    class TestGCSFileOperations:
        """GCS ファイル操作テストクラス（自己文書化）"""
        
        def test_upload_audio_file_音声ファイルアップロードで正常動作(self, comprehensive_emulator_setup):
            """音声ファイルのアップロードが正常に動作することを検証
            
            AAA パターンに従った検証項目：
            - Arrange: 模擬音声データの準備
            - Act: GCSへのアップロード実行
            - Assert: ファイル存在・サイズ・コンテンツタイプの確認
            """
            # Arrange（準備）
            env = comprehensive_emulator_setup
            file_path = f'pytest/audio/test-audio-{uuid.uuid4().hex[:8]}.wav'
            
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
        
        def test_upload_transcription_result_文字起こし結果アップロードで正常動作(self, comprehensive_emulator_setup):
            """文字起こし結果のアップロードが正常に動作することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            job_id = f'pytest-transcription-{uuid.uuid4().hex[:8]}'
            result_path = f'pytest/results/{job_id}/transcription.json'
            
            transcription_data = {
                'jobId': job_id,
                'segments': [
                    {'start': 0.0, 'end': 2.3, 'text': 'Pytestテストです', 'speaker': 'SPEAKER_01'},
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
            assert downloaded_json['segments'][0]['text'] == 'Pytestテストです', "最初のセグメントテキストが一致しません"
            assert downloaded_json['speakerCount'] == 2, "話者数が正しく保存されていません"
            assert downloaded_json['confidence'] == 0.95, "信頼度が正しく保存されていません"
            
            logger.info(f"✅ GCS文字起こし結果アップロードテスト成功: {result_path}")
        
        def test_file_metadata_operations_ファイルメタデータ操作で正常動作(self, comprehensive_emulator_setup):
            """ファイルメタデータの設定・取得が正常に動作することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            file_path = f'pytest/metadata/metadata-test-{uuid.uuid4().hex[:8]}.wav'
            file_content = b'pytest test audio content with metadata'
            
            metadata = {
                'originalFileName': 'user-upload-pytest.wav',
                'userId': 'pytest-user-123',
                'uploadTimestamp': datetime.now(timezone.utc).isoformat(),
                'processingStatus': 'queued',
                'fileVersion': '1.0',
                'testEnvironment': 'pytest-emulator',
                'contentChecksum': 'sha256-pytest-checksum',
                'audioFormat': 'wav',
                'sampleRate': '16000',
                'channels': '1'
            }
            
            # Act（実行）
            blob = env.test_bucket.blob(file_path)
            blob.metadata = metadata
            blob.upload_from_string(file_content, content_type='audio/wav')
            
            # Assert（検証）
            blob.reload()  # メタデータを最新化
            assert blob.metadata is not None, "メタデータが設定されていません"
            assert blob.metadata['originalFileName'] == 'user-upload-pytest.wav', "元ファイル名メタデータが一致しません"
            assert blob.metadata['userId'] == 'pytest-user-123', "ユーザーIDメタデータが一致しません"
            assert blob.metadata['processingStatus'] == 'queued', "処理ステータスメタデータが一致しません"
            assert blob.metadata['testEnvironment'] == 'pytest-emulator', "テスト環境メタデータが一致しません"
            assert blob.metadata['sampleRate'] == '16000', "サンプルレートメタデータが一致しません"
            
            logger.info(f"✅ GCSメタデータ操作テスト成功: {file_path}")
        
        def test_file_folder_structure_フォルダー構造操作で正常動作(self, comprehensive_emulator_setup):
            """フォルダー風構造の操作が正常に動作することを検証"""
            # Arrange（準備）
            env = comprehensive_emulator_setup
            base_id = uuid.uuid4().hex[:6]
            
            folder_files = [
                # 音声ファイル構造
                f'pytest/audio/user-123/{base_id}/original.wav',
                f'pytest/audio/user-123/{base_id}/processed.wav',
                f'pytest/audio/user-456/{base_id}/original.wav',
                
                # 結果ファイル構造
                f'pytest/results/user-123/{base_id}/transcription.json',
                f'pytest/results/user-123/{base_id}/diarization.json',
                f'pytest/results/user-456/{base_id}/transcription.json',
                
                # アーカイブ構造
                f'pytest/archive/2025/06/{base_id}/old-job.wav',
                f'pytest/temp/{base_id}/processing.tmp',
            ]
            
            # Act（実行）
            for file_path in folder_files:
                blob = env.test_bucket.blob(file_path)
                content = f'Pytest content of {file_path}'.encode('utf-8')
                blob.upload_from_string(content)
            
            # Assert（検証）
            # user-123 のファイル一覧取得
            user123_audio = list(env.test_bucket.list_blobs(prefix=f'pytest/audio/user-123/{base_id}/'))
            user123_results = list(env.test_bucket.list_blobs(prefix=f'pytest/results/user-123/{base_id}/'))
            
            assert len(user123_audio) == 2, f"user-123の音声ファイル数が期待値と異なります: {len(user123_audio)}"
            assert len(user123_results) == 2, f"user-123の結果ファイル数が期待値と異なります: {len(user123_results)}"
            
            # アーカイブフォルダーの確認
            archive_files = list(env.test_bucket.list_blobs(prefix='pytest/archive/'))
            assert len(archive_files) == 1, f"アーカイブファイル数が期待値と異なります: {len(archive_files)}"
            assert '2025/06' in archive_files[0].name, "アーカイブファイルのパス構造が正しくありません"
            
            # 一時ファイルの確認
            temp_files = list(env.test_bucket.list_blobs(prefix='pytest/temp/'))
            assert len(temp_files) == 1, f"一時ファイル数が期待値と異なります: {len(temp_files)}"
            
            logger.info(f"✅ GCSフォルダー構造操作テスト成功: base_id={base_id}")


@pytest.mark.emulator
class TestPytestWhisperEmulatorWorkflow:
    """
    Pytest版Whisper統合ワークフローテスト
    
    実際のWhisper処理フローでFirestore・GCSエミュレータの統合動作を検証
    エンドツーエンドの動作確認とエラーハンドリングの検証を含む
    """
    
    def test_complete_whisper_workflow_完全なワークフローで正常動作(self, comprehensive_emulator_setup):
        """完全なWhisperワークフローが正常に動作することを検証
        
        テストシナリオ：
        1. 音声ファイルアップロード（GCS）
        2. ジョブデータ作成（Firestore）
        3. ジョブステータス更新 → 処理中
        4. 文字起こし結果保存（GCS）
        5. ジョブ完了更新（Firestore）
        6. 最終検証（統合性確認）
        """
        # Arrange（準備）
        env = comprehensive_emulator_setup
        job_id = f'pytest-integration-{uuid.uuid4().hex[:8]}'
        user_id = f'pytest-user-{uuid.uuid4().hex[:8]}'
        original_filename = 'pytest-meeting-recording.wav'
        
        # 1. 音声ファイルアップロード（GCS）
        audio_content = b'RIFF' + (5000).to_bytes(4, 'little') + b'WAVE' + b'fmt ' + b'\x00' * 5000
        audio_path = f'pytest/audio/{job_id}/original.wav'
        
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
            'userEmail': f'{user_id}@pytest.example.com',
            'filename': original_filename,
            'gcsBucketName': env.test_bucket.name,
            'audioSize': len(audio_content),
            'audioDurationMs': 180000,  # 3分
            'fileHash': f'pytest-sha256-{job_id}',
            'status': 'queued',
            'language': 'ja',
            'initialPrompt': 'Pytestテスト用の会議録音です',
            'numSpeakers': 3,
            'minSpeakers': 1,
            'maxSpeakers': 5,
            'tags': ['pytest', 'integration', 'meeting'],
            'description': 'Pytest統合テスト用完全ワークフロー',
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
            'processingNode': 'pytest-node-001'
        })
        
        processing_doc = job_ref.get()
        processing_data = processing_doc.to_dict()
        assert processing_data['status'] == 'processing', "ステータスが処理中に更新されていません"
        assert 'processStartedAt' in processing_data, "処理開始時刻が設定されていません"
        assert processing_data['processingNode'] == 'pytest-node-001', "処理ノード情報が設定されていません"
        
        # 4. 文字起こし結果保存（GCS）
        transcription_result = {
            'jobId': job_id,
            'segments': [
                {'start': 0.0, 'end': 4.2, 'text': 'Pytestテスト会議を開始します', 'speaker': 'SPEAKER_01', 'confidence': 0.98},
                {'start': 4.2, 'end': 8.8, 'text': '今日の議題は統合テストの結果について', 'speaker': 'SPEAKER_02', 'confidence': 0.95},
                {'start': 8.8, 'end': 12.5, 'text': 'エミュレータテストが正常に動作していることを確認', 'speaker': 'SPEAKER_01', 'confidence': 0.97},
                {'start': 12.5, 'end': 16.2, 'text': 'はい、承知いたしました', 'speaker': 'SPEAKER_03', 'confidence': 0.94},
                {'start': 16.2, 'end': 20.0, 'text': 'テスト結果は良好です', 'speaker': 'SPEAKER_02', 'confidence': 0.96},
            ],
            'language': 'ja',
            'duration': 20.0,
            'processingTime': 4.5,
            'speakerCount': 3,
            'confidence': 0.96,
            'model': 'whisper-large-v3',
            'diarizationModel': 'pyannote-3.1',
            'processingTimestamp': datetime.now(timezone.utc).isoformat(),
            'statistics': {
                'totalWords': 25,
                'totalSegments': 5,
                'averageConfidence': 0.96,
                'silenceDuration': 2.5
            }
        }
        
        result_path = f'pytest/results/{job_id}/transcription.json'
        result_blob = env.test_bucket.blob(result_path)
        result_blob.upload_from_string(
            json.dumps(transcription_result, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        
        # 話者分離結果も保存
        diarization_result = {
            'jobId': job_id,
            'speakers': [
                {'speaker': 'SPEAKER_01', 'totalDuration': 8.7, 'segments': 2},
                {'speaker': 'SPEAKER_02', 'totalDuration': 7.6, 'segments': 2},
                {'speaker': 'SPEAKER_03', 'totalDuration': 3.7, 'segments': 1}
            ],
            'totalSpeakers': 3,
            'model': 'pyannote-3.1',
            'processingTimestamp': datetime.now(timezone.utc).isoformat()
        }
        
        diarization_path = f'pytest/results/{job_id}/diarization.json'
        diarization_blob = env.test_bucket.blob(diarization_path)
        diarization_blob.upload_from_string(
            json.dumps(diarization_result, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        
        # 5. ジョブ完了更新（Firestore）
        job_ref.update({
            'status': 'completed',
            'processEndedAt': env.SERVER_TIMESTAMP,
            'updatedAt': env.SERVER_TIMESTAMP,
            'completionData': {
                'transcriptionPath': result_path,
                'diarizationPath': diarization_path,
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
        assert 'completionData' in completed_data, "完了データが設定されていません"
        
        # GCSファイル存在確認
        assert audio_blob.exists(), "音声ファイルが存在しません"
        assert result_blob.exists(), "文字起こし結果ファイルが存在しません"
        assert diarization_blob.exists(), "話者分離結果ファイルが存在しません"
        
        # 結果ファイル内容検証
        downloaded_result = json.loads(result_blob.download_as_text())
        assert downloaded_result['jobId'] == job_id, "結果ファイルのジョブIDが一致しません"
        assert len(downloaded_result['segments']) == 5, "セグメント数が期待値と異なります"
        assert downloaded_result['speakerCount'] == 3, "話者数が期待値と異なります"
        assert downloaded_result['confidence'] == 0.96, "信頼度が期待値と異なります"
        
        downloaded_diarization = json.loads(diarization_blob.download_as_text())
        assert downloaded_diarization['totalSpeakers'] == 3, "話者分離結果の話者数が一致しません"
        assert len(downloaded_diarization['speakers']) == 3, "話者情報の数が一致しません"
        
        logger.info(f'✅ Pytest統合ワークフローテスト完了: {job_id}')
    
    def test_workflow_error_handling_エラーハンドリングで正常動作(self, comprehensive_emulator_setup):
        """ワークフローのエラーハンドリングが正常に動作することを検証"""
        # Arrange（準備）
        env = comprehensive_emulator_setup
        job_id = f'pytest-error-{uuid.uuid4().hex[:8]}'
        
        # エラーケース用ジョブデータ作成
        job_data = {
            'jobId': job_id,
            'userId': 'pytest-error-user',
            'userEmail': 'pytest-error@example.com',
            'filename': 'corrupted-audio.wav',
            'gcsBucketName': env.test_bucket.name,
            'audioSize': 0,  # サイズ0（破損ファイル）
            'audioDurationMs': 0,
            'fileHash': f'error-hash-{job_id}',
            'status': 'queued',
            'language': 'ja',
            'createdAt': env.SERVER_TIMESTAMP,
            'errorHistory': []
        }
        
        job_ref = env.test_collection.document(job_id)
        job_ref.set(job_data)
        
        # Act（実行）
        # エラー状態への更新
        error_message = 'Pytestテスト: 音声ファイルが破損しており、処理できませんでした'
        error_details = {
            'errorCode': 'AUDIO_CORRUPTED',
            'errorType': 'VALIDATION_ERROR',
            'errorTimestamp': datetime.now(timezone.utc).isoformat(),
            'processingNode': 'pytest-error-node',
            'stackTrace': 'pytest.error.AudioValidationError: Invalid WAV header',
            'retryCount': 0,
            'maxRetries': 3
        }
        
        job_ref.update({
            'status': 'failed',
            'errorMessage': error_message,
            'errorDetails': error_details,
            'processEndedAt': env.SERVER_TIMESTAMP,
            'updatedAt': env.SERVER_TIMESTAMP
        })
        
        # Assert（検証）
        failed_doc = job_ref.get()
        failed_data = failed_doc.to_dict()
        assert failed_data['status'] == 'failed', "エラー状態が正しく設定されていません"
        assert failed_data['errorMessage'] == error_message, "エラーメッセージが正しく保存されていません"
        assert 'processEndedAt' in failed_data, "処理終了時刻が設定されていません"
        assert 'errorDetails' in failed_data, "エラー詳細が保存されていません"
        assert failed_data['errorDetails']['errorCode'] == 'AUDIO_CORRUPTED', "エラーコードが正しく保存されていません"
        assert failed_data['errorDetails']['retryCount'] == 0, "リトライカウントが正しく保存されていません"
        
        logger.info(f'✅ Pytestエラーハンドリングテスト完了: {job_id}')


@pytest.mark.emulator
@pytest.mark.integration
class TestPytestEmulatorPerformance:
    """Pytestエミュレータパフォーマンステスト"""
    
    def test_concurrent_operations_並行操作で正常動作(self, comprehensive_emulator_setup):
        """並行操作がエミュレータで正常に動作することを検証"""
        import time
        import concurrent.futures
        
        # Arrange（準備）
        env = comprehensive_emulator_setup
        start_time = time.time()
        operation_count = 10
        
        def create_test_job(index: int) -> str:
            """個別のテストジョブを作成"""
            job_id = f'pytest-concurrent-{index}-{uuid.uuid4().hex[:6]}'
            
            # Firestoreドキュメント作成
            job_data = {
                'jobId': job_id,
                'userId': f'concurrent-user-{index}',
                'userEmail': f'concurrent-{index}@pytest.example.com',
                'filename': f'concurrent-audio-{index}.wav',
                'gcsBucketName': env.test_bucket.name,
                'audioSize': 1000 * index,
                'audioDurationMs': 5000 * index,
                'fileHash': f'concurrent-hash-{job_id}',
                'status': 'queued',
                'language': 'ja',
                'createdAt': env.SERVER_TIMESTAMP
            }
            
            doc_ref = env.test_collection.document(job_id)
            doc_ref.set(job_data)
            
            # GCSファイル作成
            audio_path = f'pytest/concurrent/{job_id}/audio.wav'
            audio_content = f'Concurrent test content {index}'.encode('utf-8') * 100
            
            blob = env.test_bucket.blob(audio_path)
            blob.upload_from_string(audio_content, content_type='audio/wav')
            
            return job_id
        
        # Act（実行）
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_test_job, i) for i in range(operation_count)]
            completed_jobs = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        elapsed_time = time.time() - start_time
        
        # Assert（検証）
        assert len(completed_jobs) == operation_count, f"作成されたジョブ数が期待値と異なります: {len(completed_jobs)}"
        
        # 全ジョブがFirestoreに存在することを確認
        for job_id in completed_jobs:
            doc_ref = env.test_collection.document(job_id)
            doc = doc_ref.get()
            assert doc.exists, f"ジョブ {job_id} がFirestoreに存在しません"
            
            # 対応するGCSファイルが存在することを確認
            audio_path = f'pytest/concurrent/{job_id}/audio.wav'
            blob = env.test_bucket.blob(audio_path)
            assert blob.exists(), f"ジョブ {job_id} の音声ファイルがGCSに存在しません"
        
        # パフォーマンス基準（30秒以内）
        assert elapsed_time < 30.0, f"並行操作が遅すぎます: {elapsed_time:.2f}秒"
        
        logger.info(f'✅ Pytest並行操作パフォーマンステスト完了: {elapsed_time:.2f}秒, ジョブ数: {len(completed_jobs)}')


if __name__ == '__main__':
    """テストファイル単体実行時の処理"""
    print("Pytest包括的エミュレータテストスイート")
    print("実行前にエミュレータが起動していることを確認してください:")
    print("python tests/app/gcp_emulator_run.py")
    print()
    print("テスト実行コマンド:")
    print("pytest tests/app/test_pytest_emulator_comprehensive.py -v -m emulator")