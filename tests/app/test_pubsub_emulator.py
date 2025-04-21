import json
import base64
import pytest
from common_utils.class_types import WhisperPubSubMessageData

@pytest.fixture(autouse=True)
def enable_subscriptable(monkeypatch):
    """
    WhisperPubSubMessageData を辞書風アクセス可能にする
    """
    monkeypatch.setattr(
        WhisperPubSubMessageData,
        "__getitem__",
        lambda self, key: getattr(self, key),
        raising=False,
    )

import base64
import pytest
from unittest.mock import patch, MagicMock
from whisper_queue.app.main import whisper_queue_pubsub
from common_utils.class_types import WhisperPubSubMessageData

# -----------------------------------------------------------------------------
# whisper_queue_pubsub のテスト（実際の Pub/Sub 通信形式を反映）
# -----------------------------------------------------------------------------

@patch("whisper_queue.app.main.process_subscription_message", autospec=True)
@patch("whisper_queue.app.main.process_next_job", autospec=True)
def test_whisper_queue_pubsub_base64_エンコード済み_JSONでOKを返すこと(mock_next, mock_process):
    """
    Pub/Sub メッセージが base64 エンコードされた JSON データの場合、
    process_subscription_message と process_next_job が呼ばれ "OK" を返すこと
    """
    # 実際の Pub/Sub では message.data は base64 でエンコードされた JSON 文字列
    envelope = {
        "event_type": "new_job",
        "job_id": "job1",
        "timestamp": "2025-04-19T00:00:00Z",
        "error_message": None,
    }
    raw_json = json.dumps(envelope)
    b64_payload = base64.b64encode(raw_json.encode('utf-8')).decode('utf-8')
    # Pub/Sub メッセージとしては JSON 文字列として送信される
    cloud_event = MagicMock()
    cloud_event.data = {"message": {"data": json.dumps(b64_payload)}}

    result = whisper_queue_pubsub(cloud_event)

    # 正常時は "OK" を返し、両関数が呼ばれる
    assert result == "OK"
    mock_process.assert_called_once()
    mock_next.assert_called_once()

@patch("whisper_queue.app.main.logger", autospec=True)
def test_whisper_queue_pubsub_不正なJSONでエラーを返すこと(mock_logger):
    """
    無効な JSON が渡された場合、(エラーメッセージ, 500) を返すこと
    """
    cloud_event = MagicMock()
    # JSON でも base64 でもない文字列
    cloud_event.data = {"message": {"data": "not a json"}}
    response, code = whisper_queue_pubsub(cloud_event)
    assert code == 500
    mock_logger.error.assert_called()
    assert isinstance(response, str) and response.startswith("Error:")
