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
from typing import Dict, Any, Generator, AsyncGenerator, Optional
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
    
    # WhisperModelのモック設定
    mock_whisper_model = MagicMock()
    mock_info = MagicMock()
    mock_info.language = "ja"
    
    # Segmentのモック
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 1.0
    mock_segment.text = "テストテキスト"
    
    # transcribeメソッドが2つの値（segments, info）を返すようにモック
    mock_whisper_model.transcribe.return_value = ([mock_segment], mock_info)
    mock_faster_whisper.WhisperModel.return_value = mock_whisper_model
    
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
    
    # Whisper Batch設定
    "COLLECTION": "whisper_jobs",
    "HF_AUTH_TOKEN": "test-hf-token",
    "DEVICE": "cpu",
    "LOCAL_TMP_DIR": "/tmp",
    "WHISPER_TRANSCRIPT_BLOB": "{file_hash}_transcription.json",
    "WHISPER_DIARIZATION_BLOB": "{file_hash}_diarization.json",
    "POLL_INTERVAL_SECONDS": "10",
    "FULL_AUDIO_PATH": "gs://test-whisper-bucket/{file_hash}.wav",
    "FULL_TRANSCRIPTION_PATH": "gs://test-whisper-bucket/{file_hash}/combine.json",
    
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


# 強化されたGCSモック実装
class EnhancedGCSBlob:
    """本番環境に近いGCS Blobシミュレーター"""
    
    def __init__(self, bucket_name: str, blob_name: str):
        self.bucket_name = bucket_name
        self.blob_name = blob_name
        self._content: Optional[bytes] = None
        self._content_type: str = "application/octet-stream"
        self._size: int = 0
        self._exists: bool = False
        
    @property
    def name(self) -> str:
        return self.blob_name
        
    @property
    def content_type(self) -> str:
        return self._content_type
        
    @content_type.setter
    def content_type(self, value: str):
        self._content_type = value
        
    @property
    def size(self) -> int:
        return self._size
        
    def exists(self, **kwargs) -> bool:
        return self._exists
        
    def upload_from_string(self, data: str, content_type: Optional[str] = None, **kwargs):
        if not isinstance(data, (str, bytes)):
            raise TypeError(f"Expected str or bytes, got {type(data)}")
        self._content = data.encode() if isinstance(data, str) else data
        self._size = len(self._content)
        self._exists = True
        if content_type:
            self._content_type = content_type
            
    def upload_from_filename(self, filename: str, content_type: Optional[str] = None, **kwargs):
        if not isinstance(filename, str):
            raise TypeError(f"filename must be str, got {type(filename)}")
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                self._content = f.read()
            self._size = len(self._content)
            self._exists = True
            if filename.endswith('.wav'):
                self._content_type = 'audio/wav'
            elif filename.endswith('.json'):
                self._content_type = 'application/json'
            elif content_type:
                self._content_type = content_type
        else:
            raise FileNotFoundError(f"File {filename} not found")
            
    def download_as_text(self, encoding: str = 'utf-8', **kwargs) -> str:
        if not self._exists:
            raise Exception(f"Blob {self.blob_name} does not exist")
        return self._content.decode(encoding) if self._content else ""
        
    def download_to_filename(self, filename: str, **kwargs):
        if not isinstance(filename, str):
            raise TypeError(f"filename must be str, got {type(filename)}")
        if not self._exists:
            raise Exception(f"Blob {self.blob_name} does not exist")
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'wb') as f:
            f.write(self._content or b'')
            
    def delete(self, **kwargs):
        self._exists = False
        self._content = None
        self._size = 0
        
    def generate_signed_url(self, expiration=None, method: str = "GET", version="v4", content_type=None, **kwargs) -> str:
        if method not in ["GET", "POST", "PUT", "DELETE"]:
            raise ValueError(f"Invalid method: {method}")
        return f"https://storage.googleapis.com/{self.bucket_name}/{self.blob_name}?signed=true"
        
    def reload(self, **kwargs):
        pass


class EnhancedGCSBucket:
    """本番環境に近いGCS Bucketシミュレーター"""
    
    def __init__(self, name: str):
        self.name = name
        self._blobs: Dict[str, EnhancedGCSBlob] = {}
        
    def blob(self, blob_name: str, **kwargs) -> EnhancedGCSBlob:
        if not isinstance(blob_name, str):
            raise TypeError(f"blob_name must be str, got {type(blob_name)}")
        if blob_name not in self._blobs:
            self._blobs[blob_name] = EnhancedGCSBlob(self.name, blob_name)
        return self._blobs[blob_name]


class EnhancedGCSClient:
    """本番環境に近いGCS Clientシミュレーター"""
    
    def __init__(self, project: Optional[str] = None, **kwargs):
        self.project = project
        self._buckets: Dict[str, EnhancedGCSBucket] = {}
        
    def bucket(self, bucket_name: str, **kwargs) -> EnhancedGCSBucket:
        if not isinstance(bucket_name, str):
            raise TypeError(f"bucket_name must be str, got {type(bucket_name)}")
        if bucket_name not in self._buckets:
            self._buckets[bucket_name] = EnhancedGCSBucket(bucket_name)
        return self._buckets[bucket_name]


@pytest.fixture
def enhanced_gcs_client() -> EnhancedGCSClient:
    """強化されたGCSクライアントのフィクスチャ"""
    client = EnhancedGCSClient(project=TEST_PROJECT_ID)
    bucket = client.bucket(TEST_BUCKET_NAME)
    audio_blob = bucket.blob("temp/test-audio.wav")
    audio_blob.upload_from_string(b"fake_audio_data", content_type="audio/wav")
    return client


@pytest.fixture
def enhanced_gcp_services(enhanced_gcs_client):
    """強化されたGCPサービスの包括的なモック（autospec付き）"""
    
    # 既存のFirestoreモック（簡略化）
    mock_firestore_client = MagicMock()
    mock_collection = MagicMock()
    mock_document = MagicMock()
    mock_query = MagicMock()
    
    complete_job_data = {
        "job_id": "test-doc-id",
        "user_id": TEST_USER["uid"],
        "user_email": TEST_USER["email"],
        "filename": "test-audio.wav",
        "gcs_bucket_name": TEST_BUCKET_NAME,
        "audio_size": 44100,
        "audio_duration_ms": 1000,
        "file_hash": "test-hash-123",
        "status": "completed",
        "created_at": "2025-06-01T10:00:00Z",
        "updated_at": "2025-06-01T10:05:00Z"
    }
    
    mock_document.id = "test-doc-id"
    mock_document.exists = True
    mock_document.to_dict.return_value = complete_job_data
    mock_document.reference = MagicMock()
    mock_document.reference.update.return_value = None
    mock_document.get.return_value = mock_document
    
    mock_query.stream.return_value = [mock_document]
    mock_query.limit.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.where.return_value = mock_query
    
    def mock_document_method(doc_id):
        doc_ref = MagicMock()
        doc_ref.id = doc_id
        doc_ref.exists = True
        doc_ref.to_dict.return_value = complete_job_data
        doc_ref.get.return_value = doc_ref
        doc_ref.reference = doc_ref
        doc_ref.update.return_value = None
        return doc_ref
    
    mock_collection.document = mock_document_method
    mock_collection.where.return_value = mock_query
    mock_collection.add.return_value = (None, mock_document.reference)
    
    mock_firestore_client.collection.return_value = mock_collection
    mock_firestore_client.batch.return_value = MagicMock()
    mock_firestore_client.transaction.return_value = MagicMock()
    
    # Pub/Sub クライアントのモック（autospec付き）
    mock_pubsub_client = MagicMock()
    mock_pubsub_client.topic_path.return_value = f"projects/{TEST_PROJECT_ID}/topics/whisper-queue"
    mock_publish_future = MagicMock()
    mock_publish_future.result.return_value = "message-id-123"
    mock_pubsub_client.publish.return_value = mock_publish_future
    
    with patch.multiple(
        'google.cloud.storage',
        Client=MagicMock(return_value=enhanced_gcs_client)
    ), patch.multiple(
        'google.cloud.firestore',
        Client=MagicMock(return_value=mock_firestore_client)
    ), patch.multiple(
        'google.cloud.pubsub_v1',
        PublisherClient=MagicMock(return_value=mock_pubsub_client)
    ):
        yield {
            "storage": enhanced_gcs_client,
            "firestore": mock_firestore_client,
            "pubsub": mock_pubsub_client
        }


@pytest.fixture
def mock_gcp_services():
    """GCPサービスの包括的なモック（従来版との互換性維持）"""
    
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
    
    # 完全なジョブデータを含むドキュメント
    complete_job_data = {
        "job_id": "test-doc-id",
        "user_id": TEST_USER["uid"],
        "user_email": TEST_USER["email"],
        "filename": "test-audio.wav",
        "gcs_bucket_name": TEST_BUCKET_NAME,
        "audio_size": 44100,
        "audio_duration_ms": 1000,
        "file_hash": "test-hash-123",
        "status": "completed",
        "created_at": "2025-06-01T10:00:00Z",
        "updated_at": "2025-06-01T10:05:00Z"
    }
    
    # Firestoreドキュメントの基本設定
    mock_document.id = "test-doc-id"
    mock_document.exists = True
    mock_document.to_dict.return_value = complete_job_data
    mock_document.reference = MagicMock()
    mock_document.reference.update.return_value = None
    mock_document.get.return_value = mock_document  # get()メソッドを追加
    
    # queryオブジェクトの設定 - streamメソッドがlist型を返すように修正
    mock_query.stream.return_value = [mock_document]
    mock_query.limit.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.where.return_value = mock_query
    
    # collectionのdocumentメソッドで新しいdocument referenceを作成する場合もモック化
    def mock_document_method(doc_id):
        """documentメソッドのモック（動的にドキュメントリファレンスを作成）"""
        doc_ref = MagicMock()
        doc_ref.id = doc_id
        doc_ref.exists = True
        doc_ref.to_dict.return_value = complete_job_data
        doc_ref.get.return_value = doc_ref  # get()メソッドが自分自身を返す
        doc_ref.reference = doc_ref
        doc_ref.update.return_value = None
        return doc_ref
    
    mock_collection.document = mock_document_method
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
            "document": mock_document,
            "complete_job_data": complete_job_data
        }


@pytest.fixture 
def mock_audio_processing():
    """音声処理関連のモック（autospec付き）"""
    
    # subprocess.Popenのautospecモック
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"1.0", b"")  # duration=1.0秒
    mock_process.returncode = 0
    
    with patch('subprocess.Popen', return_value=mock_process), \
         patch('backend.app.core.audio_utils.probe_duration', return_value=1.0), \
         patch('backend.app.core.audio_utils.convert_audio_to_wav_16k_mono'), \
         patch('os.path.getsize', return_value=44100), \
         patch('os.remove'), \
         patch('tempfile.NamedTemporaryFile') as mock_tempfile, \
         patch('shutil.which', return_value='/usr/bin/ffprobe'):  # ffprobeが存在することをシミュレート
        
        # 一時ファイルのモック設定
        mock_temp_file = MagicMock()
        mock_temp_file.name = "/tmp/test_audio.wav"
        mock_tempfile.return_value.__enter__.return_value = mock_temp_file
        
        yield {
            "probe_duration": 1.0,
            "temp_file": mock_temp_file,
            "process": mock_process
        }


@pytest.fixture
def mock_whisper_services():
    """Whisper関連サービスのモック"""
    
    # バックグラウンドタスクを無効化するモック関数
    async def mock_trigger_batch_processing(*args, **kwargs):
        """バッチ処理トリガー関数のモック（何もしない）"""
        pass
    
    # FastAPIのBackgroundTasksのadd_taskメソッドをモック化
    def mock_add_task(func, *args, **kwargs):
        """BackgroundTasksのadd_taskをモック化（実際には実行しない）"""
        pass
    
    with patch('backend.app.services.whisper_queue.enqueue_job_atomic'), \
         patch('backend.app.api.whisper_batch.trigger_whisper_batch_processing', side_effect=mock_trigger_batch_processing), \
         patch('backend.app.api.whisper_batch._get_current_processing_job_count', return_value=0), \
         patch('backend.app.api.whisper_batch._get_env_var', return_value="5"), \
         patch('backend.app.api.whisper.trigger_whisper_batch_processing', side_effect=mock_trigger_batch_processing), \
         patch('fastapi.BackgroundTasks.add_task', side_effect=mock_add_task):
        yield


@pytest.fixture 
def firestore_client():
    """Firestoreクライアントのフィクスチャ（実際のFirestoreエミュレータ使用）"""
    # テスト用のFirestoreクライアントを提供
    # 実際にはモックされたFirestoreクライアントを返す
    mock_client = MagicMock()
    mock_client.SERVER_TIMESTAMP = "mock_timestamp"
    
    # コレクションとドキュメントのモック設定
    mock_collection = MagicMock()
    mock_document = MagicMock()
    mock_document.id = "test-doc-id"
    mock_document.get.return_value = mock_document
    mock_document.to_dict.return_value = {"status": "queued"}
    mock_document.set.return_value = None
    mock_document.update.return_value = None
    
    mock_collection.document.return_value = mock_document
    mock_collection.where.return_value.order_by.return_value.limit.return_value.stream.return_value = [mock_document]
    
    mock_client.collection.return_value = mock_collection
    yield mock_client


@pytest.fixture
def gcs_client():
    """GCSクライアントのフィクスチャ"""
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    
    mock_blob.exists.return_value = True
    mock_blob.upload_from_file.return_value = None
    mock_blob.download_to_filename.return_value = None
    mock_blob.upload_from_filename.return_value = None
    
    mock_bucket.blob.return_value = mock_blob
    mock_client.bucket.return_value = mock_bucket
    
    yield mock_client


@pytest.fixture
def sample_firestore_job():
    """サンプルのFirestoreジョブデータ"""
    from common_utils.class_types import WhisperFirestoreData
    
    return WhisperFirestoreData(
        job_id="test-job-123",
        user_id=TEST_USER["uid"],
        user_email=TEST_USER["email"],
        filename="test-audio.wav",
        gcs_bucket_name=TEST_BUCKET_NAME,
        audio_size=44100,
        audio_duration_ms=1000,
        file_hash="test-hash-123",
        status="queued",
        num_speakers=1,
        min_speakers=1,
        max_speakers=1,
        language="ja",
        initial_prompt="",
        tags=["test"],
        description="テスト用音声"
    )


@pytest.fixture
def sample_transcription_result():
    """サンプルの文字起こし結果データ"""
    return [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "こんにちは"
        },
        {
            "start": 1.0,
            "end": 2.0,
            "text": "今日はいい天気ですね"
        },
        {
            "start": 2.0,
            "end": 3.0,
            "text": "ありがとうございます"
        }
    ]


@pytest.fixture
def sample_diarization_result():
    """サンプルの話者分離結果データ"""
    return [
        {
            "start": 0.0,
            "end": 1.0,
            "speaker": "SPEAKER_01"
        },
        {
            "start": 1.0,
            "end": 2.0,
            "speaker": "SPEAKER_02"
        },
        {
            "start": 2.0,
            "end": 3.0,
            "speaker": "SPEAKER_01"
        }
    ]


@pytest.fixture
def comprehensive_test_data():
    """包括的なテストデータ（バリデーション・エラーケース含む）"""
    return {
        "valid_upload_requests": [
            {
                "audio_data": "VGVzdCBhdWRpbyBkYXRhIGVuY29kZWQgaW4gYmFzZTY0",
                "filename": "test-audio.wav",
                "gcs_object": "temp/test-audio.wav",
                "original_name": "テスト音声.wav",
                "language": "ja",
                "num_speakers": 2
            },
            {
                "audio_data": "QW5vdGhlciB0ZXN0IGF1ZGlvIGRhdGE=",
                "filename": "meeting-recording.wav",
                "gcs_object": "whisper/meeting-recording.wav",
                "description": "会議の録音",
                "tags": ["meeting", "important"],
                "min_speakers": 1,
                "max_speakers": 5
            }
        ],
        "invalid_upload_requests": [
            {
                "filename": "incomplete.wav"
                # audio_dataが欠落
            },
            {
                "audio_data": 12345,  # 数値は無効
                "filename": "invalid-type.wav"
            },
            {
                "audio_data": "valid_data",
                "filename": "document.pdf"  # 音声ファイルではない
            }
        ],
        "realistic_transcription_segments": [
            {"start": 0.0, "end": 2.3, "text": "おはようございます。今日は重要な会議の録音です。"},
            {"start": 2.3, "end": 5.8, "text": "はい、よろしくお願いします。まず、プロジェクトの進捗状況についてお話しします。"},
            {"start": 5.8, "end": 9.2, "text": "現在の開発進捗は約75%で、予定より少し遅れていますが、品質は良好です。"}
        ],
        "error_scenarios": {
            "network_errors": ["Connection timeout", "Network unreachable"],
            "permission_errors": ["Insufficient permissions", "Access denied"],
            "validation_errors": ["Invalid file format", "File size too large"]
        }
    }


# 重い依存関係を持つモジュールのインポートは後で行う
@pytest_asyncio.fixture
async def async_test_client(mock_gcp_services, mock_audio_processing, mock_whisper_services):
    """非同期FastAPIテストクライアント（モック付き）"""
    # 使用時にのみインポート
    from backend.app.main import app
    from backend.app.api.auth import get_current_user
    
    # 認証依存関係をオーバーライド（テスト用）
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    
    # AsyncClientを適切に初期化
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    
    # クリーンアップ
    app.dependency_overrides.clear()


@pytest.fixture
def performance_test_config():
    """パフォーマンステスト用の設定"""
    return {
        "max_concurrent_requests": 5,
        "response_timeout_seconds": 10.0,
        "memory_threshold_mb": 100,
        "large_file_size_mb": 50,
        "stress_test_iterations": 10
    }


@pytest.fixture
def advanced_mock_behaviors():
    """高度なモック振る舞いのコレクション"""
    return {
        "gcs_error_simulation": {
            "connection_timeout": lambda: Exception("Connection timeout"),
            "permission_denied": lambda: Exception("Permission denied"),
            "quota_exceeded": lambda: Exception("Quota exceeded")
        },
        "firestore_error_simulation": {
            "document_not_found": lambda: Exception("Document not found"),
            "transaction_failed": lambda: Exception("Transaction failed"),
            "index_error": lambda: Exception("Index not found")
        },
        "whisper_processing_simulation": {
            "model_load_error": lambda: Exception("Model loading failed"),
            "transcription_error": lambda: Exception("Transcription failed"),
            "unsupported_format": lambda: Exception("Unsupported audio format")
        }
    }


@pytest.fixture
def test_data_factory():
    """テストデータのファクトリー関数"""
    class TestDataFactory:
        @staticmethod
        def create_whisper_job(job_id=None, user_id=None, status="queued", **kwargs):
            """基本的なWhisperジョブデータを作成"""
            default_data = {
                "job_id": job_id or f"test-job-{uuid.uuid4()}",
                "user_id": user_id or TEST_USER["uid"],
                "user_email": TEST_USER["email"],
                "filename": "test-audio.wav",
                "gcs_bucket_name": TEST_BUCKET_NAME,
                "audio_size": 44100,
                "audio_duration_ms": 1000,
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "status": status,
                "created_at": "2025-06-01T10:00:00Z",
                "updated_at": "2025-06-01T10:00:00Z"
            }
            default_data.update(kwargs)
            return default_data
        
        @staticmethod
        def create_upload_request(valid=True, **kwargs):
            """アップロードリクエストデータを作成"""
            if valid:
                default_data = {
                    "audio_data": "VGVzdCBhdWRpbyBkYXRhIGVuY29kZWQgaW4gYmFzZTY0",
                    "filename": "test-upload.wav",
                    "gcs_object": "temp/test-upload.wav",
                    "original_name": "テストアップロード.wav",
                    "language": "ja",
                    "num_speakers": 1
                }
            else:
                # 無効なデータ（必須フィールド欠落）
                default_data = {
                    "filename": "incomplete.wav"
                    # audio_data欠落
                }
            default_data.update(kwargs)
            return default_data
        
        @staticmethod
        def create_transcription_segments(count=3, language="ja"):
            """文字起こしセグメントを作成"""
            if language == "ja":
                sample_texts = ["こんにちは", "今日はいい天気です", "ありがとうございます", "お疲れ様でした", "また明日"]
            else:
                sample_texts = ["Hello", "Good morning", "Thank you", "Good bye", "See you later"]
            
            segments = []
            for i in range(min(count, len(sample_texts))):
                segments.append({
                    "start": float(i),
                    "end": float(i + 1),
                    "text": sample_texts[i]
                })
            return segments
    
    return TestDataFactory()


@pytest.fixture
def test_client(mock_gcp_services, mock_audio_processing, mock_whisper_services):
    """FastAPIテストクライアント（モック付き）"""
    # 使用時にのみインポート
    from backend.app.main import app
    from backend.app.api.auth import get_current_user
    
    # 認証依存関係をオーバーライド（テスト用）
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    
    with TestClient(app) as client:
        yield client
    
    # クリーンアップ
    app.dependency_overrides.clear()


# ==============================================================================
# GCPエミュレータ統合フィクスチャ（pytest用包括的エミュレータ対応）
# ==============================================================================

# エミュレータ利用可能性チェック
def check_emulator_availability():
    """エミュレータの利用可能性を詳細チェック"""
    import shutil
    import subprocess
    import os
    
    availability = {
        "firestore": False,
        "gcs": False,
        "firestore_reason": "",
        "gcs_reason": ""
    }
    
    # Firestore エミュレータチェック
    if not shutil.which('gcloud'):
        availability["firestore_reason"] = "gcloudコマンドが見つかりません"
    elif not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        availability["firestore_reason"] = "FIRESTORE_EMULATOR_HOST環境変数が設定されていません"
    else:
        try:
            emulator_host = os.environ.get('FIRESTORE_EMULATOR_HOST')
            host, port = emulator_host.split(':')
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, int(port)))
            sock.close()
            if result == 0:
                availability["firestore"] = True
            else:
                availability["firestore_reason"] = f"Firestoreエミュレータに接続できません: {emulator_host}"
        except Exception as e:
            availability["firestore_reason"] = f"Firestoreエミュレータチェックエラー: {e}"
    
    # GCS エミュレータチェック
    if not shutil.which('docker'):
        availability["gcs_reason"] = "Dockerコマンドが見つかりません"
    elif not os.environ.get('STORAGE_EMULATOR_HOST'):
        availability["gcs_reason"] = "STORAGE_EMULATOR_HOST環境変数が設定されていません"
    else:
        try:
            # Dockerデーモン動作確認
            result = subprocess.run(['docker', 'info'], capture_output=True, timeout=3)
            if result.returncode != 0:
                availability["gcs_reason"] = "Dockerデーモンが動作していません"
            else:
                # GCSエミュレータ接続確認
                emulator_host = os.environ.get('STORAGE_EMULATOR_HOST', 'http://localhost:9000')
                import urllib.request
                try:
                    with urllib.request.urlopen(f"{emulator_host}/_internal/healthcheck", timeout=2) as response:
                        if response.status == 200:
                            availability["gcs"] = True
                        else:
                            availability["gcs_reason"] = f"GCSエミュレータ健康チェック失敗: status {response.status}"
                except Exception as e:
                    availability["gcs_reason"] = f"GCSエミュレータに接続できません: {e}"
        except Exception as e:
            availability["gcs_reason"] = f"GCSエミュレータチェックエラー: {e}"
    
    return availability


@pytest.fixture(scope="session")
def emulator_availability_check():
    """エミュレータ利用可能性のセッションスコープチェック"""
    return check_emulator_availability()


@pytest.fixture
def real_firestore_client():
    """実際のFirestoreクライアント（エミュレータ接続）"""
    # エミュレータ利用可能性チェック
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        pytest.skip("Firestoreエミュレータが起動していません。FIRESTORE_EMULATOR_HOST環境変数を設定してください。")
    
    try:
        # モック解除：実際のFirestoreライブラリを使用
        import sys
        
        # 一時的にモックを解除
        original_modules = {}
        modules_to_restore = [
            'google.cloud.firestore',
            'google.cloud.firestore_v1',
            'google.api_core',
            'google.auth'
        ]
        
        for module_name in modules_to_restore:
            if module_name in sys.modules:
                original_modules[module_name] = sys.modules[module_name]
                del sys.modules[module_name]
        
        # 実際のFirestoreをインポート
        import google.cloud.firestore as firestore
        
        # エミュレータ用プロジェクトID（環境変数から取得）
        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-emulator-project')
        
        # エミュレータ用Firestoreクライアント作成
        client = firestore.Client(project=project_id)
        
        # 接続テスト
        test_collection = client.collection('connection_test')
        test_doc = test_collection.document('test')
        test_doc.set({'test': True})
        test_doc.delete()
        
        yield client
        
        # モックを復元
        for module_name, module in original_modules.items():
            sys.modules[module_name] = module
        
    except ImportError as e:
        pytest.skip(f"google-cloud-firestore not available: {e}")
    except Exception as e:
        pytest.skip(f"Firestore emulator connection failed: {e}")


@pytest.fixture
def real_gcs_client():
    """実際のGCSクライアント（エミュレータ接続）"""
    # エミュレータ利用可能性チェック
    if not os.environ.get('STORAGE_EMULATOR_HOST'):
        pytest.skip("GCSエミュレータが起動していません。STORAGE_EMULATOR_HOST環境変数を設定してください。")
    
    try:
        # モック解除：実際のStorageライブラリを使用
        import sys
        
        # 一時的にモックを解除
        original_modules = {}
        modules_to_restore = [
            'google.cloud.storage',
            'google.api_core',
            'google.auth'
        ]
        
        for module_name in modules_to_restore:
            if module_name in sys.modules:
                original_modules[module_name] = sys.modules[module_name]
                del sys.modules[module_name]
        
        # 実際のStorageをインポート
        import google.cloud.storage as storage
        
        # エミュレータ用プロジェクトID（環境変数から取得）
        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-emulator-project')
        
        # エミュレータ用GCSクライアント作成
        client = storage.Client(project=project_id)
        
        # 接続テスト用バケット作成（存在しない場合）
        bucket_name = 'test-connection-bucket'
        try:
            bucket = client.bucket(bucket_name)
            bucket.create()
        except Exception:
            # バケットが既に存在する場合
            bucket = client.bucket(bucket_name)
        
        # 接続テスト
        test_blob = bucket.blob('connection_test.txt')
        test_blob.upload_from_string('test')
        test_blob.delete()
        
        yield client
        
        # モックを復元
        for module_name, module in original_modules.items():
            sys.modules[module_name] = module
        
    except ImportError as e:
        pytest.skip(f"google-cloud-storage not available: {e}")
    except Exception as e:
        pytest.skip(f"GCS emulator connection failed: {e}")


@pytest.fixture
def emulator_test_bucket(real_gcs_client):
    """エミュレータ用テストバケットのセットアップ"""
    bucket_name = 'test-whisper-emulator-bucket'
    
    try:
        bucket = real_gcs_client.bucket(bucket_name)
        bucket.create()
    except Exception:
        # バケットが既に存在する場合
        bucket = real_gcs_client.bucket(bucket_name)
    
    yield bucket
    
    # クリーンアップ
    try:
        blobs = list(bucket.list_blobs())
        for blob in blobs:
            blob.delete()
    except Exception as e:
        logger.warning(f"テストバケットクリーンアップエラー: {e}")


@pytest.fixture
def emulator_firestore_collection(real_firestore_client):
    """エミュレータ用Firestoreテストコレクションのセットアップ"""
    collection_name = 'test_whisper_jobs'
    collection = real_firestore_client.collection(collection_name)
    
    yield collection
    
    # クリーンアップ
    try:
        docs = collection.limit(100).stream()
        for doc in docs:
            doc.reference.delete()
    except Exception as e:
        logger.warning(f"テストコレクションクリーンアップエラー: {e}")


@pytest.fixture
def comprehensive_emulator_setup(real_firestore_client, real_gcs_client, emulator_test_bucket, emulator_firestore_collection):
    """包括的なエミュレータ環境セットアップ"""
    
    class EmulatorTestEnvironment:
        def __init__(self):
            self.firestore_client = real_firestore_client
            self.gcs_client = real_gcs_client
            self.test_bucket = emulator_test_bucket
            self.test_collection = emulator_firestore_collection
            self.project_id = 'test-emulator-project'
            
        def create_test_audio_file(self, file_path: str, content: bytes = None) -> 'storage.Blob':
            """テスト用音声ファイルをGCSに作成"""
            if content is None:
                # 模擬WAVファイルコンテンツ
                content = b'RIFF' + b'\x00' * 4 + b'WAVE' + b'\x00' * 1000
            
            blob = self.test_bucket.blob(file_path)
            blob.upload_from_string(content, content_type='audio/wav')
            return blob
            
        def create_test_job_document(self, job_id: str, job_data: dict = None) -> 'firestore.DocumentReference':
            """テスト用ジョブドキュメントをFirestoreに作成"""
            if job_data is None:
                job_data = {
                    'jobId': job_id,
                    'userId': 'test-user-123',
                    'userEmail': 'test@example.com',
                    'filename': 'test-audio.wav',
                    'gcsBucketName': self.test_bucket.name,
                    'audioSize': 1000,
                    'audioDurationMs': 5000,
                    'fileHash': f'hash-{job_id}',
                    'status': 'queued',
                    'language': 'ja',
                    'createdAt': real_firestore_client.SERVER_TIMESTAMP,
                    'updatedAt': real_firestore_client.SERVER_TIMESTAMP
                }
            
            doc_ref = self.test_collection.document(job_id)
            doc_ref.set(job_data)
            return doc_ref
            
        def cleanup_all(self):
            """全テストデータのクリーンアップ"""
            # Firestoreクリーンアップ
            try:
                docs = self.test_collection.limit(100).stream()
                for doc in docs:
                    doc.reference.delete()
            except Exception as e:
                logger.warning(f"Firestoreクリーンアップエラー: {e}")
            
            # GCSクリーンアップ
            try:
                blobs = list(self.test_bucket.list_blobs())
                for blob in blobs:
                    blob.delete()
            except Exception as e:
                logger.warning(f"GCSクリーンアップエラー: {e}")
    
    env = EmulatorTestEnvironment()
    yield env
    
    # 最終クリーンアップ
    env.cleanup_all()


# エミュレータテスト用のマーカー
pytest_plugins = []

def pytest_configure(config):
    """pytest設定でカスタムマーカーを追加"""
    config.addinivalue_line(
        "markers", "emulator: mark test as emulator integration test (requires running emulators)"
    )
    config.addinivalue_line(
        "markers", "firestore_emulator: mark test as Firestore emulator test"
    )
    config.addinivalue_line(
        "markers", "gcs_emulator: mark test as GCS emulator test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


def pytest_collection_modifyitems(config, items):
    """エミュレータが利用できない場合、エミュレータテストをスキップ"""
    emulator_check = check_emulator_availability()
    
    for item in items:
        # Firestoreエミュレータマーカーのチェック
        if item.get_closest_marker("firestore_emulator") and not emulator_check["firestore"]:
            item.add_marker(pytest.mark.skip(reason=f"Firestore emulator not available: {emulator_check['firestore_reason']}"))
        
        # GCSエミュレータマーカーのチェック
        if item.get_closest_marker("gcs_emulator") and not emulator_check["gcs"]:
            item.add_marker(pytest.mark.skip(reason=f"GCS emulator not available: {emulator_check['gcs_reason']}"))
        
        # 総合エミュレータマーカーのチェック
        if item.get_closest_marker("emulator"):
            missing_emulators = []
            if not emulator_check["firestore"]:
                missing_emulators.append(f"Firestore: {emulator_check['firestore_reason']}")
            if not emulator_check["gcs"]:
                missing_emulators.append(f"GCS: {emulator_check['gcs_reason']}")
            
            if missing_emulators:
                item.add_marker(pytest.mark.skip(reason=f"Emulators not available: {', '.join(missing_emulators)}"))


# 従来のフィクスチャとの互換性のためのエイリアス
@pytest.fixture
def emulator_firestore():
    """レガシー互換性のためのエイリアス"""
    pytest.skip("Use real_firestore_client instead")


@pytest.fixture  
def emulator_gcs():
    """レガシー互換性のためのエイリアス"""
    pytest.skip("Use real_gcs_client instead")


@pytest.fixture
def enhanced_test_metrics():
    """テストメトリクスの収集と分析"""
    import time
    import psutil
    import os
    
    class TestMetrics:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.start_memory = None
            self.peak_memory = None
            self.process = psutil.Process(os.getpid())
        
        def start_measurement(self):
            self.start_time = time.time()
            self.start_memory = self.process.memory_info().rss
        
        def end_measurement(self):
            self.end_time = time.time()
            self.peak_memory = self.process.memory_info().rss
        
        def get_duration(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
        
        def get_memory_usage(self):
            if self.start_memory and self.peak_memory:
                return {
                    "start_mb": self.start_memory / 1024 / 1024,
                    "peak_mb": self.peak_memory / 1024 / 1024,
                    "increase_mb": (self.peak_memory - self.start_memory) / 1024 / 1024
                }
            return None
        
        def assert_performance_thresholds(self, max_duration_seconds=10.0, max_memory_increase_mb=50.0):
            duration = self.get_duration()
            memory_usage = self.get_memory_usage()
            
            if duration and duration > max_duration_seconds:
                raise AssertionError(f"テスト実行時間が上限を超過: {duration:.2f}s > {max_duration_seconds}s")
            
            if memory_usage and memory_usage["increase_mb"] > max_memory_increase_mb:
                raise AssertionError(f"メモリ使用量が上限を超過: {memory_usage['increase_mb']:.2f}MB > {max_memory_increase_mb}MB")
    
    return TestMetrics()
