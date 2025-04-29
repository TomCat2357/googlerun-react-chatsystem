# tests/app/test_missing_paths.py
import json, base64, pytest
from unittest.mock import patch, MagicMock
from common_utils.class_types import WhisperPubSubMessageData, WhisperFirestoreData
from whisper_queue.app import main as wq_main

# ----------------------------------------------------------------------
# 1. process_subscription_message : job_canceled
# ----------------------------------------------------------------------
@patch("whisper_queue.app.main.logger", autospec=True)
def test_process_subscription_message_job_canceled(mock_logger):
    msg = WhisperPubSubMessageData(
        job_id="job-cx",
        event_type="job_canceled",
        timestamp="2025-04-26T00:00:00Z",
        error_message=None,
    )
    wq_main.process_subscription_message(msg)
    mock_logger.info.assert_called_once_with("ジョブキャンセル: job-cx")

# ----------------------------------------------------------------------
# 2. handle_batch_completion : ドキュメントなし
# ----------------------------------------------------------------------
@patch("whisper_queue.app.main.logger", autospec=True)
@patch("whisper_queue.app.main.db", autospec=True)
def test_handle_batch_completion_doc_not_found(mock_db, mock_logger):
    # Firestore が存在しないドキュメントを返す
    mock_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_ref.get.return_value = mock_doc
    mock_db.collection.return_value.document.return_value = mock_ref

    msg = WhisperPubSubMessageData(
        job_id="missing-id",
        event_type="job_completed",
        timestamp="2025-04-26T00:00:00Z",
        error_message=None,
    )
    wq_main.handle_batch_completion(msg)
    mock_logger.error.assert_called_once_with("ジョブが見つかりません: missing-id")

# ----------------------------------------------------------------------
# 3. whisper_queue_pubsub : 必須フィールド欠落 → 500
# ----------------------------------------------------------------------
@patch("whisper_queue.app.main.logger", autospec=True)
def test_pubsub_missing_field_returns_500(mock_logger):
    # 'job_id' を欠落させた envelope
    envelope = {"event_type": "new_job", "timestamp": "2025-04-26T00:00:00Z"}
    cloud_event = MagicMock()
    cloud_event.data = {"message": {"data": json.dumps(envelope)}}

    resp, code = wq_main.whisper_queue_pubsub(cloud_event)
    assert code == 500
    mock_logger.error.assert_called()        # 具体文言までは検証しない

# ----------------------------------------------------------------------
# 4. create_batch_job : Batch API 例外パス
# ----------------------------------------------------------------------
@patch("whisper_queue.app.main.batch_v1.BatchServiceClient", autospec=True)
def test_create_batch_job_raises_error(mock_batch_cls):
    mock_batch = MagicMock()
    mock_batch_cls.return_value = mock_batch
    mock_batch.create_job.side_effect = Exception("batch-boom")

    bad_job = WhisperFirestoreData(
        job_id="bad",
        user_id="u",
        user_email="u@example.com",
        filename="a.mp3",
        description="",
        recording_date="2025-04-26",
        gcs_backet_name="b",
        audio_file_path="a",
        transcription_file_path="t",
        audio_size=1,
        audio_duration=1,
        file_hash="h",
        status="queued",
        language="ja",
        initial_prompt="",
    )

    with pytest.raises(Exception):
        wq_main.create_batch_job(bad_job)

# ----------------------------------------------------------------------
# 5. WhisperFirestoreData : status バリデーション
# ----------------------------------------------------------------------
def test_firestore_data_invalid_status():
    with pytest.raises(ValueError):
        WhisperFirestoreData(
            job_id="x",
            user_id="u",
            user_email="x@x",
            filename="a",
            description="",
            recording_date="2025-04-26",
            gcs_backet_name="b",
            audio_file_path="a",
            transcription_file_path="t",
            audio_size=1,
            audio_duration=1,
            file_hash="h",
            status="INVALID_STATUS",  # ←想定外
            language="ja",
            initial_prompt="",
        )
