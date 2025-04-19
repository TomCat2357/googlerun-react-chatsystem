# tests/app/test_main_extra.py

import json
import pytest
from unittest.mock import patch, MagicMock
from whisper_queue.app.main import (
    send_email_notification,
    process_subscription_message,
    whisper_queue_pubsub,
)
from common_utils.class_types import WhisperPubSubMessageData

# -----------------------------------------------------------------------------
# send_email_notification のテスト
# -----------------------------------------------------------------------------

@patch("whisper_queue.app.main.logger")
def test_send_email_notification_enabled_with_email(mock_logger, monkeypatch):
    """EMAIL_NOTIFICATION=true かつ有効なメールアドレスの場合、logger.info が呼ばれること"""
    monkeypatch.setenv("EMAIL_NOTIFICATION", "true")
    send_email_notification("user@example.com", "job1", "completed")
    mock_logger.info.assert_called_once_with(
        "メール通知送信: user@example.com, ジョブID: job1, 状態: completed"
    )

@patch("whisper_queue.app.main.logger")
def test_send_email_notification_disabled(mock_logger, monkeypatch):
    """EMAIL_NOTIFICATION=false の場合、メール送信処理がスキップされること"""
    monkeypatch.setenv("EMAIL_NOTIFICATION", "false")
    send_email_notification("user@example.com", "job1", "completed")
    mock_logger.info.assert_not_called()

@patch("whisper_queue.app.main.logger")
def test_send_email_notification_no_email(mock_logger, monkeypatch):
    """メールアドレスが空文字列の場合、何も実行されないこと"""
    monkeypatch.setenv("EMAIL_NOTIFICATION", "true")
    send_email_notification("", "job1", "completed")
    mock_logger.info.assert_not_called()

# -----------------------------------------------------------------------------
# process_subscription_message のテスト
# -----------------------------------------------------------------------------

@patch("whisper_queue.app.main.logger")
def test_process_subscription_message_new_job(mock_logger):
    """event_type=new_job のとき、新規ジョブ受信ログが出力されること"""
    msg = WhisperPubSubMessageData(
        job_id="job1",
        event_type="new_job",
        timestamp="2025-04-19T00:00:00Z",
        error_message=None,
    )
    process_subscription_message(msg)
    mock_logger.info.assert_called_with("新規ジョブ受信: job1")

@patch("whisper_queue.app.main.handle_batch_completion")
@patch("whisper_queue.app.main.logger")
def test_process_subscription_message_completed(mock_logger, mock_handle):
    """event_type=job_completed のとき、handle_batch_completion が呼ばれること"""
    msg = WhisperPubSubMessageData(
        job_id="job2",
        event_type="job_completed",
        timestamp="2025-04-19T00:00:00Z",
        error_message=None,
    )
    process_subscription_message(msg)
    mock_handle.assert_called_once_with(msg)

@patch("whisper_queue.app.main.logger")
def test_process_subscription_message_unknown_event(mock_logger):
    """不明な event_type のとき、警告ログが出力されること"""
    msg = WhisperPubSubMessageData(
        job_id="job3",
        event_type="foobar",
        timestamp="2025-04-19T00:00:00Z",
        error_message=None,
    )
    process_subscription_message(msg)
    mock_logger.warning.assert_called_once()

@patch("whisper_queue.app.main.logger")
def test_process_subscription_message_missing_job_id(mock_logger):
    """job_id が空文字列の場合、エラーログが出力されること"""
    msg = WhisperPubSubMessageData(
        job_id="",
        event_type="new_job",
        timestamp="2025-04-19T00:00:00Z",
        error_message=None,
    )
    process_subscription_message(msg)
    mock_logger.error.assert_called_once_with("必須フィールドがありません: job_id")

# -----------------------------------------------------------------------------
# whisper_queue_pubsub のテスト
# -----------------------------------------------------------------------------

@patch("whisper_queue.app.main.process_subscription_message")
@patch("whisper_queue.app.main.process_next_job")
def test_whisper_queue_pubsub_ok(mock_next, mock_process, monkeypatch):
    """正常な CloudEvent データが渡された場合、両関数が呼ばれ "OK" を返すこと"""
    envelope = {
        "event_type": "new_job",
        "job_id": "job1",
        "timestamp": "2025-04-19T00:00:00Z",
        "error_message": None,
    }
    json_data = json.dumps(envelope)
    cloud_event = MagicMock()
    cloud_event.data = {"message": {"data": json_data}}
    result = whisper_queue_pubsub(cloud_event)
    assert result == "OK"
    mock_process.assert_called_once()
    mock_next.assert_called_once()

def test_whisper_queue_pubsub_invalid_json():
    """無効な JSON が渡された場合、(エラーメッセージ, 500) を返すこと"""
    cloud_event = MagicMock()
    cloud_event.data = {"message": {"data": "not a json"}}
    response, code = whisper_queue_pubsub(cloud_event)
    assert code == 500
    assert response.startswith("Error: ")
