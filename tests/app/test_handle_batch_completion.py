# tests/app/test_handle_batch_completion.py

import pytest
from unittest.mock import patch, MagicMock
from common_utils.class_types import WhisperPubSubMessageData
from whisper_queue.app.main import handle_batch_completion

@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """テスト用の環境変数を設定"""
    monkeypatch.setenv("WHISPER_JOBS_COLLECTION", "batch_jobs")
    # メール通知を有効化
    monkeypatch.setenv("EMAIL_NOTIFICATION", "true")

class TestHandleBatchCompletion:
    """handle_batch_completion のテスト"""

    @patch("whisper_queue.app.main.send_email_notification", autospec=True)
    @patch("whisper_queue.app.main.db", autospec=True)
    def test_handle_batch_completion_completed(self, mock_db, mock_send_email):
        # --- Arrange ---
        job_id = "job-123"
        # Firestore から返ってくるドキュメントをモック
        stored = {
            "job_id": job_id,
            "user_id": "user-1",
            "user_email": "user@example.com",
            "filename": "f.mp3",
            "description": "",
            "recording_date": "2025-04-19",
            "gcs_backet_name": "bucket",
            "audio_file_path": "a.mp3",
            "transcription_file_path": "t.json",
            "audio_size": 0,
            "audio_duration": 0,
            "file_hash": "h",
            "status": "processing",
            # 他の必須フィールドも入れてください
        }
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = stored

        mock_ref = MagicMock()
        mock_ref.get.return_value = mock_doc

        # db.collection(...).document(...) → mock_ref
        mock_db.collection.return_value.document.return_value = mock_ref

        # Pub/Sub メッセージデータ
        msg = WhisperPubSubMessageData(
            event_type="job_completed",
            job_id=job_id,
            timestamp="2025-04-19T00:00:00Z",
            error_message=None,
        )

        # --- Act ---
        handle_batch_completion(msg)

        # --- Assert ---
        # Firestore 更新
        mock_db.collection.assert_called_once_with("batch_jobs")
        mock_db.collection.return_value.document.assert_called_once_with(job_id)
        update_arg = mock_ref.update.call_args[0][0]
        assert update_arg["status"] == "completed"
        assert "process_ended_at" in update_arg and "updated_at" in update_arg

        # メール送信が呼ばれる
        mock_send_email.assert_called_once_with(
            stored["user_email"], job_id, "completed"
        )

    @patch("whisper_queue.app.main.send_email_notification", autospec=True)
    @patch("whisper_queue.app.main.db", autospec=True)
    def test_handle_batch_completion_failed(self, mock_db, mock_send_email):
        # --- Arrange ---
        job_id = "job-456"
        stored = {
            "job_id": job_id,
            "user_id": "user-2",
            "user_email": "user2@example.com",
            "filename": "f2.mp3",
            "description": "",
            "recording_date": "2025-04-19",
            "gcs_backet_name": "bucket",
            "audio_file_path": "a2.mp3",
            "transcription_file_path": "t2.json",
            "audio_size": 0,
            "audio_duration": 0,
            "file_hash": "h2",
            "status": "processing",
        }
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = stored

        mock_ref = MagicMock()
        mock_ref.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value = mock_ref

        msg = WhisperPubSubMessageData(
            event_type="job_failed",
            job_id=job_id,
            timestamp="2025-04-19T00:00:00Z",
            error_message="something went wrong",
        )

        # --- Act ---
        handle_batch_completion(msg)

        # --- Assert ---
        mock_db.collection.assert_called_once_with("batch_jobs")
        mock_db.collection.return_value.document.assert_called_once_with(job_id)
        update_arg = mock_ref.update.call_args[0][0]
        assert update_arg["status"] == "failed"
        assert update_arg["error_message"] == "something went wrong"

        # 失敗時はメール送信しない
        mock_send_email.assert_not_called()
