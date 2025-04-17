#%%
import os
import pytest
from unittest.mock import patch, MagicMock
from whisper_queue.app.main import create_batch_job
from common_utils.class_types import WhisperFirestoreData
from google.cloud.batch_v1 import BatchServiceClient
from google.cloud.batch_v1.types import Runnable

@pytest.fixture
def mock_job_data():
    """テスト用のWhisperFirestoreDataを作成するフィクスチャ"""
    return WhisperFirestoreData(
        job_id="test-job-123",
        user_id="test-user-456",
        user_email="test@example.com",
        filename="test_audio.mp3",
        description="テスト用音声ファイル",
        recording_date="2025-04-17",
        gcs_backet_name="test-bucket",
        audio_file_path="audio/test_audio.mp3",
        transcription_file_path="transcriptions/test_audio.json",
        audio_size=1024000,  # 1MBほど
        audio_duration=120,  # 2分の音声
        file_hash="abcdef123456",
        status="queued",
        language="ja",
        initial_prompt="これはテスト用の音声です"
    )

# 修正アプローチ: 
# 1. BatchServiceClientだけモック化
# 2. create_batch_jobの内部で問題になる部分をモンキーパッチで一時的に修正
@patch('whisper_queue.app.main.batch_v1.BatchServiceClient')
def test_create_batch_job(mock_batch_client_class, mock_job_data, monkeypatch):
    """create_batch_job関数のテスト - 必要最小限のモック化"""
    # モックの設定
    mock_batch_client = MagicMock()
    mock_batch_client_class.return_value = mock_batch_client
    
    # create_jobメソッドの戻り値を設定
    mock_created_job = MagicMock()
    mock_created_job.name = f"projects/test-project/locations/us-central1/jobs/whisper-{mock_job_data.job_id}"
    mock_created_job.status.state = "QUEUED"
    mock_created_job.uid = "test-uuid-789"
    mock_batch_client.create_job.return_value = mock_created_job
    
    
    # テスト対象の関数を実行
    batch_job_name = create_batch_job(mock_job_data)
    
    # create_jobが呼ばれたことを確認
    mock_batch_client.create_job.assert_called_once()
    
    # 正しいジョブIDがセットされているか確認
    assert mock_job_data.job_id in batch_job_name
    
    # 関数がバッチジョブ名を返したことを確認
    assert "whisper-" in batch_job_name
    
    # リクエストの内容をチェック
    request = mock_batch_client.create_job.call_args[0][0]
    assert request.job is not None  # ジョブオブジェクトが設定されている
    
    return batch_job_name