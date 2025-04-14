"""
テスト用のヘルパー関数とモックオブジェクトを提供するモジュール
"""
import json
import datetime
import base64
from unittest.mock import MagicMock
from common_utils.class_types import WhisperFirestoreData, WhisperPubSubMessageData


def create_sample_job_data():
    """テスト用のジョブデータを作成"""
    return WhisperFirestoreData(
        job_id="test-job-123",
        user_id="test-user",
        user_email="test@example.com",
        filename="test.mp3",
        gcs_backet_name="test-bucket",
        audio_file_path="audio/test.mp3",
        transcription_file_path="transcripts/test.json",
        audio_size=1000,
        audio_duration=300,
        file_hash="test-hash",
        status="queued",
        min_speakers=1,
        max_speakers=6
    )


def create_sample_pubsub_msg(event_type="job_completed", with_error=False):
    """テスト用のPub/Subメッセージを作成"""
    kwargs = {
        "job_id": "test-job-123",
        "event_type": event_type,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    if with_error:
        kwargs["error_message"] = "テストエラーメッセージ"
        
    return WhisperPubSubMessageData(**kwargs)


def create_mock_cloud_event(event_type="job_completed"):
    """テスト用のCloud Eventモックを作成"""
    event = MagicMock()
    event_data = {
        "job_id": "test-job-123",
        "event_type": event_type,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    encoded_data = base64.b64encode(json.dumps(event_data).encode("utf-8")).decode("utf-8")
    
    event.data = {
        "message": {
            "data": encoded_data
        }
    }
    
    return event


def create_mock_firestore():
    """テスト用のFirestoreモックを作成"""
    mock_db = MagicMock()
    
    # ドキュメント参照のモック
    mock_doc_ref = MagicMock()
    mock_collection = MagicMock()
    
    # コレクションとドキュメントのチェーンをモック
    mock_db.collection.return_value = mock_collection
    mock_collection.document.return_value = mock_doc_ref
    
    # ドキュメント操作をモック
    mock_doc_ref.get.return_value = MagicMock(
        exists=True,
        to_dict=lambda: {
            "job_id": "test-job-123",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.mp3",
            "gcs_backet_name": "test-bucket",
            "audio_file_path": "audio/test.mp3",
            "transcription_file_path": "transcripts/test.json",
            "audio_size": 1000,
            "audio_duration": 300,
            "file_hash": "test-hash",
            "status": "queued",
            "min_speakers": 1,
            "max_speakers": 6
        }
    )
    
    # クエリをモック
    mock_query = MagicMock()
    mock_collection.where.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    
    # 処理中ジョブカウントをモック
    mock_count_snapshot = MagicMock()
    mock_count_snapshot.__getitem__.return_value = [(0,)]
    mock_query.count.return_value.get.return_value = mock_count_snapshot
    
    # ジョブリストをモック
    mock_job_doc = MagicMock()
    mock_job_doc.to_dict.return_value = {
        "job_id": "test-job-123",
        "status": "queued",
        "user_email": "test@example.com",
        "gcs_backet_name": "test-bucket",
        "audio_file_path": "audio/test.mp3",
        "transcription_file_path": "transcripts/test.json",
        "file_hash": "test-hash",
        "audio_duration": 300,
        "min_speakers": 1,
        "max_speakers": 6
    }
    mock_query.stream.return_value = [mock_job_doc]
    
    # トランザクションをモック
    mock_transaction = MagicMock()
    mock_db.transaction.return_value = mock_transaction
    
    return mock_db
