"""
Whisperテスト用の共通設定とフィクスチャ
"""

import pytest
import asyncio
import tempfile
import os
import json
import uuid
from pathlib import Path
from typing import Dict, Any, Generator, AsyncGenerator
from unittest.mock import Mock, patch, MagicMock

import numpy as np
from pydub import AudioSegment
from google.cloud import firestore, storage
from fastapi.testclient import TestClient
from httpx import AsyncClient

# プロジェクトのモジュール
from common_utils.gcp_emulator import firestore_emulator_context, gcs_emulator_context
from common_utils.class_types import WhisperFirestoreData, WhisperSegment
from backend.app.main import app
from backend.app.api.auth import get_current_user

# テスト用の設定
TEST_PROJECT_ID = "test-whisper-project"
TEST_BUCKET_NAME = "test-whisper-bucket"
FIRESTORE_EMULATOR_PORT = 8085
GCS_EMULATOR_PORT = 9005

# テスト用のユーザー情報
TEST_USER = {
    "uid": "test-user-123",
    "email": "test-user@example.com",
    "name": "Test User"
}


@pytest.fixture(scope="session")
def event_loop():
    """セッションスコープのイベントループ"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def emulator_setup():
    """FirestoreとGCSエミュレータのセットアップ（セッションスコープ）"""
    # Firestoreエミュレータ
    with firestore_emulator_context(
        project_id=TEST_PROJECT_ID,
        port=FIRESTORE_EMULATOR_PORT
    ) as fs_emulator:
        # GCSエミュレータ
        with gcs_emulator_context(
            project_id=TEST_PROJECT_ID,
            port=GCS_EMULATOR_PORT
        ) as gcs_emulator:
            # テスト用バケットの作成
            gcs_client = storage.Client(project=TEST_PROJECT_ID)
            try:
                gcs_client.create_bucket(TEST_BUCKET_NAME)
            except Exception:
                pass  # バケットが既に存在する場合は無視
            
            yield {
                "firestore": fs_emulator,
                "gcs": gcs_emulator,
                "project_id": TEST_PROJECT_ID,
                "bucket_name": TEST_BUCKET_NAME
            }


@pytest.fixture
async def firestore_client(emulator_setup):
    """Firestoreクライアントのフィクスチャ"""
    client = firestore.Client(project=TEST_PROJECT_ID)
    yield client


@pytest.fixture
async def gcs_client(emulator_setup):
    """GCSクライアントのフィクスチャ"""
    client = storage.Client(project=TEST_PROJECT_ID)
    yield client


@pytest.fixture
def mock_auth_user():
    """認証ユーザーのモック"""
    with patch("backend.app.api.whisper.get_current_user", return_value=TEST_USER):
        yield TEST_USER


@pytest.fixture
async def test_client():
    """FastAPIテストクライアント"""
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_test_client():
    """非同期FastAPIテストクライアント"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_audio_file():
    """テスト用の音声ファイル（WAV形式）を生成"""
    # 1秒間の440Hzのサイン波を生成
    sample_rate = 16000
    duration_ms = 1000
    frequency = 440
    
    # NumPyで音声波形を生成
    t = np.linspace(0, duration_ms / 1000, int(sample_rate * duration_ms / 1000), False)
    wave = np.sin(2 * np.pi * frequency * t) * 0.3
    audio_data = (wave * 32767).astype(np.int16)
    
    # PyDubのAudioSegmentに変換
    audio = AudioSegment(
        audio_data.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1
    )
    
    # 一時ファイルに保存
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        audio.export(tmp_file.name, format="wav")
        yield tmp_file.name
    
    # クリーンアップ
    if os.path.exists(tmp_file.name):
        os.remove(tmp_file.name)


@pytest.fixture
def sample_firestore_job():
    """テスト用のFirestoreジョブデータ"""
    job_id = str(uuid.uuid4())
    return WhisperFirestoreData(
        job_id=job_id,
        user_id=TEST_USER["uid"],
        user_email=TEST_USER["email"],
        filename="test_audio.wav",
        description="テスト用音声ファイル",
        recording_date="2025-05-29",
        gcs_bucket_name=TEST_BUCKET_NAME,
        audio_size=44100,
        audio_duration_ms=1000,
        file_hash="test_hash_123",
        language="ja",
        initial_prompt="",
        status="queued",
        tags=["test"],
        num_speakers=1,
        min_speakers=1,
        max_speakers=1
    )


@pytest.fixture
def sample_whisper_segments():
    """テスト用のWhisperセグメントデータ"""
    return [
        WhisperSegment(
            start=0.0,
            end=1.0,
            text="こんにちは",
            speaker="SPEAKER_01"
        ),
        WhisperSegment(
            start=1.0,
            end=2.0,
            text="世界",
            speaker="SPEAKER_01"
        )
    ]


@pytest.fixture
def mock_whisper_model():
    """Whisperモデルのモック"""
    mock_info = Mock()
    mock_info.language = "ja"
    
    mock_segments = [
        Mock(start=0.0, end=1.0, text="こんにちは"),
        Mock(start=1.0, end=2.0, text="世界")
    ]
    
    mock_model = Mock()
    mock_model.transcribe.return_value = (mock_segments, mock_info)
    
    with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model):
        yield mock_model


@pytest.fixture
def mock_gcp_services():
    """GCPサービスのモック（エミュレータを使わない場合）"""
    with patch("google.cloud.firestore.Client") as mock_firestore, \
         patch("google.cloud.storage.Client") as mock_storage, \
         patch("google.cloud.pubsub_v1.PublisherClient") as mock_pubsub:
        
        # Firestoreモック
        mock_fs_client = Mock()
        mock_firestore.return_value = mock_fs_client
        
        # GCSモック
        mock_gcs_client = Mock()
        mock_storage.return_value = mock_gcs_client
        
        # Pub/Subモック
        mock_ps_client = Mock()
        mock_pubsub.return_value = mock_ps_client
        
        yield {
            "firestore": mock_fs_client,
            "storage": mock_gcs_client,
            "pubsub": mock_ps_client
        }


@pytest.fixture
def temp_directory():
    """一時ディレクトリのフィクスチャ"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_transcription_result():
    """テスト用の文字起こし結果"""
    return [
        {"start": 0.0, "end": 1.0, "text": "こんにちは"},
        {"start": 1.0, "end": 2.0, "text": "世界"}
    ]


@pytest.fixture
def sample_diarization_result():
    """テスト用の話者分離結果"""
    return [
        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
        {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"}
    ]


@pytest.fixture
def mock_environment_variables():
    """環境変数のモック"""
    env_vars = {
        "GCP_PROJECT_ID": TEST_PROJECT_ID,
        "GCS_BUCKET_NAME": TEST_BUCKET_NAME,
        "GCS_BUCKET": TEST_BUCKET_NAME,
        "WHISPER_JOBS_COLLECTION": "whisper_jobs",
        "WHISPER_MAX_SECONDS": "1800",
        "WHISPER_MAX_BYTES": "104857600",
        "GENERAL_LOG_MAX_LENGTH": "1000",
        "SENSITIVE_KEYS": "password,secret",
        "PUBSUB_TOPIC": "whisper-queue",
        "WHISPER_AUDIO_BLOB": "whisper/{file_hash}.{ext}",
        "WHISPER_COMBINE_BLOB": "{file_hash}/combine.json",
        "PROCESS_TIMEOUT_SECONDS": "300",
        "AUDIO_TIMEOUT_MULTIPLIER": "2.0",
        "FIRESTORE_MAX_DAYS": "30"
    }
    
    with patch.dict(os.environ, env_vars):
        yield env_vars


# テストヘルパー関数
def create_test_job_in_firestore(firestore_client: firestore.Client, job_data: WhisperFirestoreData):
    """Firestoreにテスト用ジョブを作成"""
    doc_ref = firestore_client.collection("whisper_jobs").document(job_data.job_id)
    doc_ref.set(job_data.model_dump())
    return doc_ref


def upload_test_file_to_gcs(gcs_client: storage.Client, bucket_name: str, blob_name: str, content: bytes):
    """GCSにテストファイルをアップロード"""
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content)
    return blob
