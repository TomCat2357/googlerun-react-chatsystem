import pytest
from unittest.mock import patch, MagicMock, call
import os
from google.cloud import firestore
from whisper_queue.app.main import process_next_job, create_batch_job
from common_utils.class_types import WhisperFirestoreData

@pytest.fixture
def mock_firestore_client():
    """Firestoreクライアントのモックを作成するフィクスチャ"""
    with patch('whisper_queue.app.main.db', autospec=True) as mock_db:
        # トランザクションメソッドのモック
        mock_transaction = MagicMock()
        mock_db.transaction.return_value = mock_transaction
        
        yield mock_db

@pytest.fixture
def mock_env_vars():
    """環境変数のモックを作成するフィクスチャ"""
    with patch.dict('os.environ', {
        'MAX_PROCESSING_JOBS': '2',
        'WHISPER_JOBS_COLLECTION': 'test_whisper_jobs'
    }):
        yield

def create_mock_job_data(job_id):
    """テスト用のWhisperFirestoreDataを作成"""
    return WhisperFirestoreData(
        job_id=job_id,
        user_id=f"user-{job_id}",
        user_email=f"user-{job_id}@example.com",
        filename=f"test_{job_id}.mp3",
        description="テスト用音声ファイル",
        recording_date="2025-04-17",
        gcs_backet_name="test-bucket",
        audio_file_path=f"audio/test_{job_id}.mp3",
        transcription_file_path=f"transcriptions/test_{job_id}.json",
        audio_size=1024000,  # 1MBほど
        audio_duration=120,  # 2分の音声
        file_hash=f"hash-{job_id}",
        status="queued",
        language="ja",
        initial_prompt="これはテスト用の音声です"
    )

# トランザクション内でFirestoreからジョブを取得するケース
@patch('whisper_queue.app.main.create_batch_job', autospec=True)
def test_process_next_job_available_slots(mock_create_batch_job, mock_firestore_client, mock_env_vars):
    """処理待ちのジョブがあり、スロットが空いている場合のテスト"""
    # モックの設定
    mock_collection = MagicMock()
    mock_firestore_client.collection.return_value = mock_collection
    
    # 処理中のジョブ数のモック化
    mock_processing_count_query = MagicMock()
    mock_collection.where.return_value.count.return_value = mock_processing_count_query
    mock_processing_count_query.get.return_value = [(1,)]  # 現在1つのジョブが処理中
    
    # 処理待ちのジョブのモック化
    mock_queued_query = MagicMock()
    mock_collection.where.return_value.order_by.return_value.limit.return_value = mock_queued_query
    
    # 取得するジョブデータの作成
    job1 = create_mock_job_data("job1")
    job2 = create_mock_job_data("job2")
    
    # ドキュメントスナップショットのモック化
    mock_doc1 = MagicMock()
    mock_doc1.to_dict.return_value = job1.model_dump()
    mock_doc1.id = job1.job_id
    
    mock_doc2 = MagicMock()
    mock_doc2.to_dict.return_value = job2.model_dump()
    mock_doc2.id = job2.job_id
    
    mock_queued_query.stream.return_value = [mock_doc1, mock_doc2]
    
    # ドキュメント参照のモック化
    mock_doc_ref = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    
    # create_batch_jobの戻り値設定
    mock_create_batch_job.return_value = "whisper-job1-1234567890"
    
    # テスト対象の関数を実行
    process_next_job()
    
    # 検証
    # Firestoreのコレクションが正しく参照されたか
    mock_firestore_client.collection.assert_has_calls([
        call('test_whisper_jobs'),  # 処理中ジョブカウント用
        call('test_whisper_jobs'),  # 処理待ちジョブ取得用
        call('test_whisper_jobs'),  # ジョブ参照用 (job1)
        call('test_whisper_jobs')   # ジョブ参照用 (job2)
    ])
    
    # ステータスが"processing"に更新されたか
    assert mock_doc_ref.update.call_count == 2
    
    # バッチジョブが作成されたか
    assert mock_create_batch_job.call_count == 2

# スロットが空いていないケース
@patch('whisper_queue.app.main.create_batch_job', autospec=True)
def test_process_next_job_no_available_slots(mock_create_batch_job, mock_firestore_client, mock_env_vars):
    """スロットが空いていない場合のテスト"""
    # モックの設定
    mock_collection = MagicMock()
    mock_firestore_client.collection.return_value = mock_collection
    
    # 処理中のジョブ数のモック化
    mock_processing_count_query = MagicMock()
    mock_collection.where.return_value.count.return_value = mock_processing_count_query
    mock_processing_count_query.get.return_value = [(2,)]  # すでに2つのジョブが処理中
    
    # テスト対象の関数を実行
    process_next_job()
    
    # 検証
    # 処理中ジョブ数の確認のみが行われるはず
    mock_firestore_client.collection.assert_called_once_with('test_whisper_jobs')
    mock_collection.where.assert_called_once_with('status', '==', 'processing')
    
    # ジョブ取得やバッチジョブ作成は行われないはず
    mock_collection.where.return_value.order_by.assert_not_called()
    mock_create_batch_job.assert_not_called()

# 処理待ちのジョブがないケース
@patch('whisper_queue.app.main.create_batch_job', autospec=True)
def test_process_next_job_no_queued_jobs(mock_create_batch_job, mock_firestore_client, mock_env_vars):
    """処理待ちのジョブがない場合のテスト"""
    # モックの設定
    mock_collection = MagicMock()
    mock_firestore_client.collection.return_value = mock_collection
    
    # 処理中のジョブ数のモック化
    mock_processing_count_query = MagicMock()
    mock_collection.where.return_value.count.return_value = mock_processing_count_query
    mock_processing_count_query.get.return_value = [(0,)]  # 処理中のジョブなし
    
    # 処理待ちのジョブのモック化
    mock_queued_query = MagicMock()
    mock_collection.where.return_value.order_by.return_value.limit.return_value = mock_queued_query
    
    # 空のリストを返す
    mock_queued_query.stream.return_value = []
    
    # テスト対象の関数を実行
    process_next_job()
    
    # 検証
    # Firestoreからジョブ取得は行われるが、空なのでバッチジョブ作成は行われないはず
    mock_collection.where.return_value.order_by.return_value.limit.assert_called_once()
    mock_create_batch_job.assert_not_called()

# バッチジョブ作成時にエラーが発生するケース
@patch('whisper_queue.app.main.create_batch_job', autospec=True)
def test_process_next_job_batch_creation_error(mock_create_batch_job, mock_firestore_client, mock_env_vars):
    """バッチジョブ作成時にエラーが発生する場合のテスト"""
    # モックの設定
    mock_collection = MagicMock()
    mock_firestore_client.collection.return_value = mock_collection
    
    # 処理中のジョブ数のモック化
    mock_processing_count_query = MagicMock()
    mock_collection.where.return_value.count.return_value = mock_processing_count_query
    mock_processing_count_query.get.return_value = [(0,)]  # 処理中のジョブなし
    
    # 処理待ちのジョブのモック化
    mock_queued_query = MagicMock()
    mock_collection.where.return_value.order_by.return_value.limit.return_value = mock_queued_query
    
    # 取得するジョブデータの作成
    job = create_mock_job_data("job_error")
    
    # ドキュメントスナップショットのモック化
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = job.model_dump()
    mock_doc.id = job.job_id
    
    mock_queued_query.stream.return_value = [mock_doc]
    
    # ドキュメント参照のモック化
    mock_doc_ref = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    
    # create_batch_jobが例外を投げるよう設定
    mock_create_batch_job.side_effect = Exception("バッチジョブ作成エラー")
    
    # テスト対象の関数を実行
    process_next_job()
    
    # 検証
    # バッチジョブ作成が試みられたか
    mock_create_batch_job.assert_called_once()
    
    # エラーが発生したのでステータスがfailedに更新されたか
    mock_doc_ref.update.assert_called_once()
    update_data = mock_doc_ref.update.call_args[0][0]
    assert update_data['status'] == 'failed'
    assert 'error_message' in update_data
    assert update_data['error_message'].startswith('バッチジョブ作成エラー')
