"""
最小限のテスト設定（重い依存関係を除外）
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import json
import uuid
import sys
from pathlib import Path
from typing import Dict, Any, Generator, AsyncGenerator
from unittest.mock import Mock, patch, MagicMock

import numpy as np
from pydub import AudioSegment
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# 重いライブラリを事前にモック化（インポート前に実行）
def mock_heavy_modules():
    """重いGoogle CloudライブラリとVertexAIをモック化"""
    
    # Google認証を最初にモック化（他のすべてのGoogle Cloudライブラリより前）
    mock_google_auth = MagicMock()
    mock_credentials = MagicMock()
    mock_google_auth.default.return_value = (mock_credentials, "test-project")
    mock_google_auth.exceptions = MagicMock()
    mock_google_auth.exceptions.DefaultCredentialsError = Exception
    mock_google_auth.credentials = MagicMock()
    sys.modules['google.auth'] = mock_google_auth
    sys.modules['google.auth._default'] = MagicMock()
    sys.modules['google.auth.exceptions'] = mock_google_auth.exceptions
    sys.modules['google.auth.credentials'] = mock_google_auth.credentials
    
    # Google API Core関連のモック
    mock_api_core = MagicMock()
    mock_api_core.client_options = MagicMock()
    mock_api_core.gapic_v1 = MagicMock()
    mock_api_core.grpc_helpers = MagicMock()
    sys.modules['google.api_core'] = mock_api_core
    sys.modules['google.api_core.client_options'] = mock_api_core.client_options
    sys.modules['google.api_core.gapic_v1'] = mock_api_core.gapic_v1
    sys.modules['google.api_core.gapic_v1.method'] = MagicMock()
    sys.modules['google.api_core.grpc_helpers'] = mock_api_core.grpc_helpers
    
    # Google Cloud共通基盤のモック
    mock_cloud_client = MagicMock()
    sys.modules['google.cloud.client'] = mock_cloud_client
    sys.modules['google.cloud._helpers'] = MagicMock()
    
    # Google Cloud Secret Manager関連のモック
    mock_secretmanager = MagicMock()
    mock_secretmanager_client = MagicMock()
    mock_secretmanager.SecretManagerServiceClient = MagicMock(return_value=mock_secretmanager_client)
    sys.modules['google.cloud.secretmanager'] = mock_secretmanager
    sys.modules['google.cloud.secretmanager_v1'] = mock_secretmanager
    
    # Google Cloud Firestore関連のモック（詳細）
    mock_firestore = MagicMock()
    mock_firestore_client = MagicMock()
    mock_firestore.Client = MagicMock(return_value=mock_firestore_client)
    mock_firestore.SERVER_TIMESTAMP = "mock_timestamp"
    sys.modules['google.cloud.firestore'] = mock_firestore
    sys.modules['google.cloud.firestore_v1'] = mock_firestore
    sys.modules['google.cloud.firestore_v1.client'] = MagicMock()
    sys.modules['google.cloud.firestore_v1.base_client'] = MagicMock()
    sys.modules['google.cloud.firestore_v1._helpers'] = MagicMock()
    
    # Google Cloud Storage関連のモック
    mock_storage = MagicMock()
    mock_storage_client = MagicMock()
    mock_storage.Client = MagicMock(return_value=mock_storage_client)
    sys.modules['google.cloud.storage'] = mock_storage
    
    # Google Cloud Pub/Sub関連のモック
    mock_pubsub = MagicMock()
    mock_pubsub_client = MagicMock()
    mock_pubsub.PublisherClient = MagicMock(return_value=mock_pubsub_client)
    sys.modules['google.cloud.pubsub_v1'] = mock_pubsub
    
    # VertexAI関連のモック
    mock_vertexai = MagicMock()
    mock_vertexai.init = MagicMock()
    mock_vertexai.generative_models = MagicMock()
    mock_vertexai_preview = MagicMock()
    mock_vertexai_preview.generative_models = MagicMock()
    mock_vertexai_preview.vision_models = MagicMock()
    mock_vertexai.preview = mock_vertexai_preview
    sys.modules['vertexai'] = mock_vertexai
    sys.modules['vertexai.generative_models'] = mock_vertexai.generative_models
    sys.modules['vertexai.preview'] = mock_vertexai_preview
    sys.modules['vertexai.preview.generative_models'] = mock_vertexai_preview.generative_models
    sys.modules['vertexai.preview.vision_models'] = mock_vertexai_preview.vision_models
    
    # Google Cloud AI Platform関連のモック
    mock_aiplatform = MagicMock()
    sys.modules['google.cloud.aiplatform'] = mock_aiplatform
    sys.modules['google.cloud.aiplatform.gapic'] = MagicMock()
    sys.modules['google.cloud.aiplatform.v1'] = MagicMock()
    sys.modules['google.cloud.aiplatform.v1beta1'] = MagicMock()
    
    # Google Cloud Speech関連のモック  
    mock_speech = MagicMock()
    mock_speech_client = MagicMock()
    mock_speech.SpeechClient = MagicMock(return_value=mock_speech_client)
    mock_speech_types = MagicMock()
    mock_speech.types = mock_speech_types
    sys.modules['google.cloud.speech'] = mock_speech
    sys.modules['google.cloud.speech_v1'] = MagicMock()
    sys.modules['google.cloud.speech_v2'] = mock_speech
    sys.modules['google.cloud.speech_v2.types'] = mock_speech_types
    
    # Firebase Admin関連のモック（一部）
    mock_firebase_admin = MagicMock()
    mock_firebase_admin.get_app = MagicMock(side_effect=ValueError("No app"))  # 初期化されていない状態
    mock_firebase_admin.initialize_app = MagicMock()
    mock_firebase_admin.credentials = MagicMock()
    mock_firebase_admin.credentials.Certificate = MagicMock()
    mock_firebase_admin.auth = MagicMock()
    mock_firebase_admin.auth.verify_id_token = MagicMock()
    sys.modules['firebase_admin'] = mock_firebase_admin
    sys.modules['firebase_admin.auth'] = mock_firebase_admin.auth
    sys.modules['firebase_admin.credentials'] = mock_firebase_admin.credentials
    
    # Hypercorn（本番サーバー）のモック
    sys.modules['hypercorn'] = MagicMock()
    sys.modules['hypercorn.asyncio'] = MagicMock()
    sys.modules['hypercorn.config'] = MagicMock()
    
    # その他の重いGoogle Cloudライブラリ
    mock_batch = MagicMock()
    mock_batch_types = MagicMock()
    # Batch関連の詳細なモック
    mock_batch_types.Job = MagicMock()
    mock_batch_types.TaskSpec = MagicMock()
    mock_batch_types.TaskGroup = MagicMock()
    mock_batch_types.Runnable = MagicMock()
    mock_batch_types.Environment = MagicMock()
    mock_batch_types.Resources = MagicMock()
    mock_batch_types.AllocationPolicy = MagicMock()
    mock_batch_types.LogsPolicy = MagicMock()
    mock_batch_types.JobStatus = MagicMock()
    mock_batch_types.JobNotification = MagicMock()
    mock_batch.types = mock_batch_types
    
    sys.modules['google.cloud.batch'] = mock_batch
    sys.modules['google.cloud.batch_v1'] = mock_batch
    sys.modules['google.cloud.batch_v1.types'] = mock_batch_types
    sys.modules['google.cloud.tasks'] = MagicMock()
    sys.modules['google.cloud.tasks_v2'] = MagicMock()
    
    # docx2txt（ファイル処理）
    sys.modules['docx2txt'] = MagicMock()
    
    # PyTorch関連のモック（Whisperで使用）
    mock_torch = MagicMock()
    mock_torch.cuda = MagicMock()
    mock_torch.cuda.is_available = MagicMock(return_value=False)
    mock_torch.jit = MagicMock()
    mock_torch.nn = MagicMock()
    mock_torch.device = MagicMock()
    sys.modules['torch'] = mock_torch
    sys.modules['torch.nn'] = mock_torch.nn
    sys.modules['torch.jit'] = mock_torch.jit
    sys.modules['torch.cuda'] = mock_torch.cuda
    
    # torchaudio関連のモック
    mock_torchaudio = MagicMock()
    mock_torchaudio.load = MagicMock()
    mock_torchaudio.save = MagicMock()
    mock_torchaudio.transforms = MagicMock()
    sys.modules['torchaudio'] = mock_torchaudio
    sys.modules['torchaudio.transforms'] = mock_torchaudio.transforms
    
    # faster-whisper関連のモック
    mock_faster_whisper = MagicMock()
    sys.modules['faster_whisper'] = mock_faster_whisper
    
    # whisperやwhisper関連ライブラリのモック
    mock_whisper = MagicMock()
    sys.modules['whisper'] = mock_whisper
    
    # pyannote関連のモック（話者分離で使用）
    mock_pyannote = MagicMock()
    sys.modules['pyannote'] = mock_pyannote
    sys.modules['pyannote.audio'] = MagicMock()
    sys.modules['pyannote.audio.pipelines'] = MagicMock()
    sys.modules['pyannote.core'] = MagicMock()
    
    # transformers関連のモック（Hugging Face）
    mock_transformers = MagicMock()
    sys.modules['transformers'] = mock_transformers
    
    # librosa関連のモック（音声処理）
    mock_librosa = MagicMock()
    sys.modules['librosa'] = mock_librosa
    
    # scipy関連のモック（科学計算）
    mock_scipy = MagicMock()
    sys.modules['scipy'] = mock_scipy
    sys.modules['scipy.io'] = MagicMock()
    sys.modules['scipy.signal'] = MagicMock()

# 重いモジュールをモック化
mock_heavy_modules()

# 環境変数を最初に設定（モジュールインポート前）
os.environ.update({
    # Firebase設定
    "FIREBASE_CLIENT_SECRET_PATH": "",
    
    # フロントエンド設定
    "FRONTEND_PATH": "/tmp/frontend",
    
    # CORS設定
    "ORIGINS": "http://localhost:5173,http://localhost:5174",
    
    # IP制限設定
    "ALLOWED_IPS": "127.0.0.0/24",
    
    # ログ設定
    "LOGOUT_LOG_MAX_LENGTH": "100",
    "CONFIG_LOG_MAX_LENGTH": "300",
    "VERIFY_AUTH_LOG_MAX_LENGTH": "200",
    "SPEECH2TEXT_LOG_MAX_LENGTH": "1200",
    "GENERATE_IMAGE_LOG_MAX_LENGTH": "500",
    "GENERAL_LOG_MAX_LENGTH": "1000",
    "MIDDLE_WARE_LOG_MAX_LENGTH": "1000",
    "GEOCODING_LOG_MAX_LENGTH": "1000",
    "CHAT_LOG_MAX_LENGTH": "1000",
    
    # センシティブキー設定
    "SENSITIVE_KEYS": "password,secret",
    
    # Google Cloud設定
    "GCP_PROJECT_ID": "test-whisper-project",
    "GCP_REGION": "us-central1",
    "VERTEX_PROJECT": "test-whisper-project",
    "VERTEX_LOCATION": "us-central1",
    "GOOGLE_APPLICATION_CREDENTIALS": "",
    
    # GCS設定
    "GCS_BUCKET_NAME": "test-whisper-bucket",
    "GCS_BUCKET": "test-whisper-bucket",
    
    # Whisper設定
    "WHISPER_JOBS_COLLECTION": "whisper_jobs",
    "WHISPER_MAX_SECONDS": "1800",
    "WHISPER_MAX_BYTES": "104857600",
    "WHISPER_AUDIO_BLOB": "whisper/{file_hash}.{ext}",
    "WHISPER_COMBINE_BLOB": "{file_hash}/combine.json",
    
    # Pub/Sub設定
    "PUBSUB_TOPIC": "whisper-queue",
    
    # プロセス設定
    "PROCESS_TIMEOUT_SECONDS": "300",
    "AUDIO_TIMEOUT_MULTIPLIER": "2.0",
    
    # Firestore設定
    "FIRESTORE_MAX_DAYS": "30",
    
    # AIモデル設定
    "MODELS": "gemini-2.0-flash-001,gemini-2.0-flash-lite-preview-02-05",
    
    # 画像生成設定
    "IMAGEN_MODELS": "imagen-3.0-generate-002,imagen-3.0-generate-001",
    "IMAGEN_NUMBER_OF_IMAGES": "1,2,3,4",
    "IMAGEN_ASPECT_RATIOS": "1:1,9:16,16:9,4:3,3:4",
    "IMAGEN_LANGUAGES": "auto,en,ja",
    "IMAGEN_ADD_WATERMARK": "true,false",
    "IMAGEN_SAFETY_FILTER_LEVELS": "block_medium_and_above",
    "IMAGEN_PERSON_GENERATIONS": "allow_adult",
    
    # ファイルサイズ制限
    "MAX_PAYLOAD_SIZE": "268435456",
    "MAX_IMAGES": "10",
    "MAX_LONG_EDGE": "1568",
    "MAX_IMAGE_SIZE": "5242880",
    "MAX_AUDIO_FILES": "1",
    "MAX_TEXT_FILES": "10",
    "MAX_AUDIO_BYTES": "104857600",
    "MAX_AUDIO_BASE64_CHARS": "157286400",
    
    # 音声設定
    "SPEECH_MAX_SECONDS": "10800",
    
    # Google Maps設定
    "GOOGLE_MAPS_API_KEY_PATH": "",
    "SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY": "",
    "GOOGLE_MAPS_API_CACHE_TTL": "2592000",
    "GEOCODING_NO_IMAGE_MAX_BATCH_SIZE": "300",
    "GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE": "30",
    "GEOCODING_BATCH_SIZE": "5",
    
    # バッチ処理設定
    "MAX_PROCESSING_JOBS": "5",
    "BATCH_JOB_TIMEOUT_SECONDS": "3600",
    "BATCH_REGION": "us-central1",
    "BATCH_SERVICE_ACCOUNT": "test-service-account@test-project.iam.gserviceaccount.com",
    
    # SSL設定
    "SSL_CERT_PATH": "",
    "SSL_KEY_PATH": "",
    
    # リクエストID不要パス
    "UNNEED_REQUEST_ID_PATH": "",
    "UNNEED_REQUEST_ID_PATH_STARTSWITH": "",
    "UNNEED_REQUEST_ID_PATH_ENDSWITH": "",
})

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


# event_loopフィクスチャは削除（pytest-asyncioのデフォルトを使用）


@pytest.fixture
def mock_auth_user():
    """認証ユーザーのモック"""
    # 認証関数を直接モック化し、常にTEST_USERを返すようにする
    async def mock_get_current_user(*args, **kwargs):
        return TEST_USER
        
    with patch('backend.app.api.whisper.get_current_user', side_effect=mock_get_current_user), \
         patch('backend.app.api.auth.get_current_user', side_effect=mock_get_current_user), \
         patch('firebase_admin.auth.verify_id_token', return_value=TEST_USER):
        yield TEST_USER


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
def temp_directory():
    """一時ディレクトリのフィクスチャ"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


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


@pytest.fixture
def mock_gcp_services():
    """GCPサービスの包括的なモック"""
    
    # Google Cloud Storageモック
    mock_gcs_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    
    # Blobの基本設定
    mock_blob.exists.return_value = True
    mock_blob.content_type = "audio/wav"
    mock_blob.size = 44100
    mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"
    mock_blob.download_as_text.return_value = '[]'
    mock_blob.upload_from_string.return_value = None
    mock_blob.upload_from_filename.return_value = None
    mock_blob.download_to_filename.return_value = None
    mock_blob.delete.return_value = None
    
    mock_bucket.blob.return_value = mock_blob
    mock_bucket.create_bucket.return_value = None
    mock_gcs_client.bucket.return_value = mock_bucket
    mock_gcs_client.create_bucket.return_value = None
    
    # Google Cloud Firestoreモック
    mock_firestore_client = MagicMock()
    mock_collection = MagicMock()
    mock_document = MagicMock()
    mock_query = MagicMock()
    
    # Firestoreドキュメントの基本設定
    mock_document.id = "test-doc-id"
    mock_document.exists = True
    mock_document.to_dict.return_value = {"status": "completed", "user_id": TEST_USER["uid"]}
    mock_document.reference = MagicMock()
    mock_document.reference.update.return_value = None
    
    mock_query.stream.return_value = [mock_document]
    mock_query.limit.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.where.return_value = mock_query
    
    mock_collection.document.return_value = mock_document
    mock_collection.where.return_value = mock_query
    mock_collection.add.return_value = (None, mock_document.reference)
    
    mock_firestore_client.collection.return_value = mock_collection
    mock_firestore_client.batch.return_value = MagicMock()
    mock_firestore_client.transaction.return_value = MagicMock()
    
    # Google Cloud Pub/Subモック
    mock_pubsub_client = MagicMock()
    mock_pubsub_client.topic_path.return_value = "projects/test-project/topics/test-topic"
    mock_publish_future = MagicMock()
    mock_publish_future.result.return_value = "message-id"
    mock_pubsub_client.publish.return_value = mock_publish_future
    
    with patch.multiple(
        'google.cloud.storage',
        Client=MagicMock(return_value=mock_gcs_client)
    ), patch.multiple(
        'google.cloud.firestore',
        Client=MagicMock(return_value=mock_firestore_client)
    ), patch.multiple(
        'google.cloud.pubsub_v1',
        PublisherClient=MagicMock(return_value=mock_pubsub_client)
    ):
        yield {
            "storage": mock_gcs_client,
            "firestore": mock_firestore_client,
            "pubsub": mock_pubsub_client,
            "bucket": mock_bucket,
            "blob": mock_blob,
            "document": mock_document
        }


@pytest.fixture 
def mock_audio_processing():
    """音声処理関連のモック"""
    with patch('app.core.audio_utils.probe_duration', return_value=1.0), \
         patch('app.core.audio_utils.convert_audio_to_wav_16k_mono'), \
         patch('os.path.getsize', return_value=44100), \
         patch('os.remove'), \
         patch('tempfile.NamedTemporaryFile') as mock_tempfile:
        
        # 一時ファイルのモック設定
        mock_temp_file = MagicMock()
        mock_temp_file.name = "/tmp/test_audio.wav"
        mock_tempfile.return_value.__enter__.return_value = mock_temp_file
        
        yield {
            "probe_duration": 1.0,
            "temp_file": mock_temp_file
        }


@pytest.fixture
def mock_whisper_services():
    """Whisper関連サービスのモック"""
    with patch('app.services.whisper_queue.enqueue_job_atomic'), \
         patch('app.api.whisper_batch.trigger_whisper_batch_processing'), \
         patch('app.api.whisper_batch._get_current_processing_job_count', return_value=0), \
         patch('app.api.whisper_batch._get_env_var', return_value="5"):
        yield


# 重い依存関係を持つモジュールのインポートは後で行う
@pytest_asyncio.fixture
async def async_test_client(mock_gcp_services, mock_audio_processing, mock_whisper_services):
    """非同期FastAPIテストクライアント（モック付き）"""
    # 使用時にのみインポート
    from backend.app.main import app
    
    # AsyncClientを適切に初期化
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def test_client(mock_gcp_services, mock_audio_processing, mock_whisper_services):
    """FastAPIテストクライアント（モック付き）"""
    # 使用時にのみインポート
    from backend.app.main import app
    with TestClient(app) as client:
        yield client
