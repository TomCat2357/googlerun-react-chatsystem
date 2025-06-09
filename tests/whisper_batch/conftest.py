"""
Whisperバッチ処理テスト用設定

音声処理とバッチジョブテストに特化したフィクスチャとモック設定
"""

import pytest
import tempfile
import os
import json
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import Mock, patch, MagicMock

import numpy as np
from pydub import AudioSegment


# ==============================================================================
# Audio Test Data Fixtures
# ==============================================================================

@pytest.fixture
def test_audio_samples():
    """テスト用音声サンプルデータセット"""
    sample_rate = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    return {
        "short_mono": (np.sin(2 * np.pi * 440 * t[:8000]) * 0.5).astype(np.float32),  # 0.5秒
        "long_mono": (np.sin(2 * np.pi * 880 * t) * 0.3).astype(np.float32),        # 2秒
        "quiet": (np.sin(2 * np.pi * 220 * t) * 0.1).astype(np.float32),           # 小音量
        "loud": (np.sin(2 * np.pi * 1760 * t) * 0.9).astype(np.float32),          # 大音量
    }


@pytest.fixture
def temp_audio_files(test_audio_samples):
    """一時音声ファイルセット"""
    files = {}
    temp_files = []
    
    for name, audio_data in test_audio_samples.items():
        temp_file = tempfile.NamedTemporaryFile(suffix=f"_{name}.wav", delete=False)
        
        # 16bit PCMに変換
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # WAVファイルとして保存
        audio_segment = AudioSegment(
            audio_int16.tobytes(),
            frame_rate=16000,
            sample_width=2,
            channels=1
        )
        audio_segment.export(temp_file.name, format="wav")
        
        files[name] = temp_file.name
        temp_files.append(temp_file.name)
    
    yield files
    
    # クリーンアップ
    for file_path in temp_files:
        if os.path.exists(file_path):
            os.unlink(file_path)


# ==============================================================================
# Batch Processing Mocks
# ==============================================================================

@pytest.fixture
def mock_whisper_model():
    """Whisperモデルのモック"""
    mock_model = MagicMock()
    
    # 文字起こし結果のモック
    mock_result = {
        "text": "こんにちは、これはテスト音声です。",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 2.5,
                "text": "こんにちは、これはテスト音声です。",
                "confidence": 0.95
            }
        ],
        "language": "ja"
    }
    
    mock_model.transcribe.return_value = mock_result
    return mock_model


@pytest.fixture
def mock_diarization_pipeline():
    """話者分離パイプラインのモック"""
    mock_pipeline = MagicMock()
    
    # 話者分離結果のモック
    mock_diarization = MagicMock()
    mock_diarization.get_timeline.return_value = [
        (0.0, 1.2, "SPEAKER_00"),
        (1.2, 2.5, "SPEAKER_01")
    ]
    
    mock_pipeline.return_value = mock_diarization
    return mock_pipeline


@pytest.fixture
def mock_gcp_batch_client():
    """GCP Batchクライアントのモック"""
    mock_client = MagicMock()
    
    # ジョブ作成結果のモック
    mock_job = MagicMock()
    mock_job.name = "projects/test-project/locations/us-central1/jobs/whisper-job-12345"
    mock_job.state = "QUEUED"
    
    mock_client.create_job.return_value = mock_job
    mock_client.get_job.return_value = mock_job
    
    return mock_client


# ==============================================================================
# Pytest Markers
# ==============================================================================

def pytest_configure(config):
    """pytest設定の初期化（Whisperバッチ用）"""
    config.addinivalue_line(
        "markers", "audio_processing: audio processing tests"
    )
    config.addinivalue_line(
        "markers", "batch_jobs: batch job tests"
    )
    config.addinivalue_line(
        "markers", "speaker_diarization: speaker separation tests"
    )
    config.addinivalue_line(
        "markers", "performance: performance tests"
    )
    config.addinivalue_line(
        "markers", "slow: slow running tests"
    )
