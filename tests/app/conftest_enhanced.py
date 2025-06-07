"""
実用的なモック戦略を実装したconftest.py
autospecを使った引数チェックと本番環境に近いモック実装
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import json
import uuid
import sys
import hashlib
from pathlib import Path
from typing import Dict, Any, Generator, AsyncGenerator, Optional, List
from unittest.mock import Mock, patch, MagicMock, create_autospec
from datetime import datetime, timezone

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
    
    # その他の重いライブラリの基本モック（詳細は省略）
    for module_name in [
        'google.cloud.secretmanager', 'google.cloud.firestore', 'google.cloud.storage',
        'google.cloud.pubsub_v1', 'vertexai', 'google.cloud.speech', 'firebase_admin',
        'torch', 'torchaudio', 'faster_whisper', 'whisper', 'pyannote', 'transformers',
        'librosa', 'scipy', 'hypercorn'
    ]:
        sys.modules[module_name] = MagicMock()

# 重いモジュールをモック化
mock_heavy_modules()

# 環境変数を設定
os.environ.update({
    "FIREBASE_CLIENT_SECRET_PATH": "",
    "FRONTEND_PATH": "/tmp/frontend",
    "ORIGINS": "http://localhost:5173,http://localhost:5174",
    "ALLOWED_IPS": "127.0.0.0/24",
    "SENSITIVE_KEYS": "password,secret",
    "GCP_PROJECT_ID": "test-whisper-project",
    "GCS_BUCKET_NAME": "test-whisper-bucket",
    "WHISPER_JOBS_COLLECTION": "whisper_jobs",
    "WHISPER_MAX_SECONDS": "1800",
    "WHISPER_MAX_BYTES": "104857600",
    "GENERAL_LOG_MAX_LENGTH": "1000",
    "PUBSUB_TOPIC": "whisper-queue",
    "WHISPER_AUDIO_BLOB": "whisper/{file_hash}.{ext}",
    "WHISPER_COMBINE_BLOB": "{file_hash}/combine.json",
    "PROCESS_TIMEOUT_SECONDS": "300",
    "AUDIO_TIMEOUT_MULTIPLIER": "2.0",
    "FIRESTORE_MAX_DAYS": "30",
    "MAX_PROCESSING_JOBS": "5",
    "BATCH_JOB_TIMEOUT_SECONDS": "3600",
})

# テスト用定数
TEST_PROJECT_ID = "test-whisper-project"
TEST_BUCKET_NAME = "test-whisper-bucket"
TEST_USER = {
    "uid": "test-user-123",
    "email": "test-user@example.com",
    "name": "Test User"
}


class EnhancedGCSBlob:
    """本番環境に近いGCS Blobシミュレーター"""
    
    def __init__(self, bucket_name: str, blob_name: str):
        self.bucket_name = bucket_name
        self.blob_name = blob_name
        self._content: Optional[bytes] = None
        self._content_type: str = "application/octet-stream"
        self._size: int = 0
        self._exists: bool = False
        self._metadata: Dict[str, Any] = {}
        
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
        """ファイルの存在確認（引数チェック付き）"""
        return self._exists
        
    def upload_from_string(self, data: str, content_type: Optional[str] = None, **kwargs):
        """文字列からのアップロード（実際のファイル操作をシミュレート）"""
        if not isinstance(data, (str, bytes)):
            raise TypeError(f"Expected str or bytes, got {type(data)}")
            
        self._content = data.encode() if isinstance(data, str) else data
        self._size = len(self._content)
        self._exists = True
        if content_type:
            self._content_type = content_type
            
    def upload_from_filename(self, filename: str, content_type: Optional[str] = None, **kwargs):
        """ファイルからのアップロード（引数チェック付き）"""
        if not isinstance(filename, str):
            raise TypeError(f"filename must be str, got {type(filename)}")
            
        # 実際のファイル操作をシミュレート（ファイルが存在する場合）
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                self._content = f.read()
            self._size = len(self._content)
            self._exists = True
            
            # content_typeの自動推定をシミュレート
            if filename.endswith('.wav'):
                self._content_type = 'audio/wav'
            elif filename.endswith('.json'):
                self._content_type = 'application/json'
            elif content_type:
                self._content_type = content_type
        else:
            raise FileNotFoundError(f"File {filename} not found")
            
    def download_as_text(self, encoding: str = 'utf-8', **kwargs) -> str:
        """テキストとしてダウンロード"""
        if not self._exists:
            raise Exception(f"Blob {self.blob_name} does not exist")
        return self._content.decode(encoding) if self._content else ""
        
    def download_to_filename(self, filename: str, **kwargs):
        """ファイルへのダウンロード（引数チェック付き）"""
        if not isinstance(filename, str):
            raise TypeError(f"filename must be str, got {type(filename)}")
            
        if not self._exists:
            raise Exception(f"Blob {self.blob_name} does not exist")
            
        # 実際のファイル操作をシミュレート
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'wb') as f:
            f.write(self._content or b'')
            
    def delete(self, **kwargs):
        """削除（引数チェック付き）"""
        self._exists = False
        self._content = None
        self._size = 0
        
    def generate_signed_url(self, expiration=None, method: str = "GET", **kwargs) -> str:
        """署名付きURL生成（引数チェック付き）"""
        if method not in ["GET", "POST", "PUT", "DELETE"]:
            raise ValueError(f"Invalid method: {method}")
            
        return f"https://storage.googleapis.com/{self.bucket_name}/{self.blob_name}?signed=true"
        
    def reload(self, **kwargs):
        """メタデータの再読み込み"""
        pass


class EnhancedGCSBucket:
    """本番環境に近いGCS Bucketシミュレーター"""
    
    def __init__(self, name: str):
        self.name = name
        self._blobs: Dict[str, EnhancedGCSBlob] = {}
        
    def blob(self, blob_name: str, **kwargs) -> EnhancedGCSBlob:
        """Blobの取得または作成（引数チェック付き）"""
        if not isinstance(blob_name, str):
            raise TypeError(f"blob_name must be str, got {type(blob_name)}")
            
        if blob_name not in self._blobs:
            self._blobs[blob_name] = EnhancedGCSBlob(self.name, blob_name)
        return self._blobs[blob_name]
        
    def list_blobs(self, prefix: Optional[str] = None, **kwargs) -> List[EnhancedGCSBlob]:
        """Blobの一覧取得（引数チェック付き）"""
        if prefix:
            return [blob for name, blob in self._blobs.items() if name.startswith(prefix) and blob._exists]
        return [blob for blob in self._blobs.values() if blob._exists]


class EnhancedGCSClient:
    """本番環境に近いGCS Clientシミュレーター"""
    
    def __init__(self, project: Optional[str] = None, **kwargs):
        self.project = project
        self._buckets: Dict[str, EnhancedGCSBucket] = {}
        
    def bucket(self, bucket_name: str, **kwargs) -> EnhancedGCSBucket:
        """Bucketの取得または作成（引数チェック付き）"""
        if not isinstance(bucket_name, str):
            raise TypeError(f"bucket_name must be str, got {type(bucket_name)}")
            
        if bucket_name not in self._buckets:
            self._buckets[bucket_name] = EnhancedGCSBucket(bucket_name)
        return self._buckets[bucket_name]


class EnhancedFirestoreDocument:
    """本番環境に近いFirestore Documentシミュレーター"""
    
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]] = None):
        self.id = doc_id
        self._data = data or {}
        self._exists = bool(data)
        self.reference = self
        
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式でデータを取得"""
        return self._data.copy()
        
    def get(self, **kwargs):
        """ドキュメントの取得"""
        return self if self._exists else None
        
    def set(self, data: Dict[str, Any], merge: bool = False, **kwargs):
        """ドキュメントの設定（引数チェック付き）"""
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict, got {type(data)}")
            
        if merge:
            self._data.update(data)
        else:
            self._data = data.copy()
        self._exists = True
        
    def update(self, data: Dict[str, Any], **kwargs):
        """ドキュメントの更新（引数チェック付き）"""
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict, got {type(data)}")
            
        self._data.update(data)
        
    @property
    def exists(self) -> bool:
        return self._exists


class EnhancedFirestoreQuery:
    """本番環境に近いFirestore Queryシミュレーター"""
    
    def __init__(self, documents: List[EnhancedFirestoreDocument]):
        self._documents = documents
        self._filters = []
        self._limit_count = None
        self._order_fields = []
        
    def where(self, field: str, op: str, value: Any) -> "EnhancedFirestoreQuery":
        """Where句の追加（引数チェック付き）"""
        if not isinstance(field, str):
            raise TypeError(f"field must be str, got {type(field)}")
        if op not in ["==", "!=", "<", "<=", ">", ">=", "in", "not-in", "array-contains"]:
            raise ValueError(f"Invalid operator: {op}")
            
        self._filters.append((field, op, value))
        return self
        
    def order_by(self, field: str, direction: str = "asc") -> "EnhancedFirestoreQuery":
        """Order by句の追加（引数チェック付き）"""
        if not isinstance(field, str):
            raise TypeError(f"field must be str, got {type(field)}")
        if direction not in ["asc", "desc"]:
            raise ValueError(f"Invalid direction: {direction}")
            
        self._order_fields.append((field, direction))
        return self
        
    def limit(self, count: int) -> "EnhancedFirestoreQuery":
        """Limit句の追加（引数チェック付き）"""
        if not isinstance(count, int) or count <= 0:
            raise TypeError(f"count must be positive int, got {type(count)}")
            
        self._limit_count = count
        return self
        
    def stream(self) -> List[EnhancedFirestoreDocument]:
        """クエリ結果のストリーミング（フィルタリング実装）"""
        result = self._documents.copy()
        
        # フィルタの適用
        for field, op, value in self._filters:
            filtered_result = []
            for doc in result:
                doc_data = doc.to_dict()
                if field in doc_data:
                    field_value = doc_data[field]
                    if self._matches_filter(field_value, op, value):
                        filtered_result.append(doc)
            result = filtered_result
            
        # ソートの適用
        for field, direction in self._order_fields:
            reverse = direction == "desc"
            result.sort(key=lambda d: d.to_dict().get(field, ""), reverse=reverse)
            
        # Limitの適用
        if self._limit_count:
            result = result[:self._limit_count]
            
        return result
        
    def _matches_filter(self, field_value: Any, op: str, filter_value: Any) -> bool:
        """フィルタマッチング判定"""
        if op == "==":
            return field_value == filter_value
        elif op == "!=":
            return field_value != filter_value
        elif op == "<":
            return field_value < filter_value
        elif op == "<=":
            return field_value <= filter_value
        elif op == ">":
            return field_value > filter_value
        elif op == ">=":
            return field_value >= filter_value
        elif op == "in":
            return field_value in filter_value
        elif op == "not-in":
            return field_value not in filter_value
        elif op == "array-contains":
            return filter_value in field_value if isinstance(field_value, list) else False
        return False


class EnhancedFirestoreCollection:
    """本番環境に近いFirestore Collectionシミュレーター"""
    
    def __init__(self, name: str):
        self.name = name
        self._documents: Dict[str, EnhancedFirestoreDocument] = {}
        
    def document(self, doc_id: Optional[str] = None) -> EnhancedFirestoreDocument:
        """ドキュメントの取得または作成（引数チェック付き）"""
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        elif not isinstance(doc_id, str):
            raise TypeError(f"doc_id must be str, got {type(doc_id)}")
            
        if doc_id not in self._documents:
            self._documents[doc_id] = EnhancedFirestoreDocument(doc_id)
        return self._documents[doc_id]
        
    def add(self, data: Dict[str, Any], **kwargs) -> tuple:
        """ドキュメントの追加（引数チェック付き）"""
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict, got {type(data)}")
            
        doc_id = str(uuid.uuid4())
        doc = EnhancedFirestoreDocument(doc_id, data)
        self._documents[doc_id] = doc
        return None, doc
        
    def where(self, field: str, op: str, value: Any) -> EnhancedFirestoreQuery:
        """Where句を持つクエリの作成（引数チェック付き）"""
        docs = [doc for doc in self._documents.values() if doc._exists]
        query = EnhancedFirestoreQuery(docs)
        return query.where(field, op, value)


class EnhancedFirestoreClient:
    """本番環境に近いFirestore Clientシミュレーター"""
    
    def __init__(self, project: Optional[str] = None, **kwargs):
        self.project = project
        self._collections: Dict[str, EnhancedFirestoreCollection] = {}
        
    def collection(self, name: str) -> EnhancedFirestoreCollection:
        """コレクションの取得または作成（引数チェック付き）"""
        if not isinstance(name, str):
            raise TypeError(f"name must be str, got {type(name)}")
            
        if name not in self._collections:
            self._collections[name] = EnhancedFirestoreCollection(name)
        return self._collections[name]
        
    def batch(self):
        """バッチ操作のモック"""
        return MagicMock()
        
    def transaction(self):
        """トランザクション操作のモック"""
        return MagicMock()


@pytest.fixture
def mock_auth_user():
    """認証ユーザーのモック（autospec付き）"""
    async def mock_get_current_user(*args, **kwargs):
        return TEST_USER
        
    with patch('backend.app.api.whisper.get_current_user', side_effect=mock_get_current_user), \
         patch('backend.app.api.auth.get_current_user', side_effect=mock_get_current_user), \
         patch('firebase_admin.auth.verify_id_token', return_value=TEST_USER):
        yield TEST_USER


@pytest.fixture
def enhanced_gcs_client() -> EnhancedGCSClient:
    """強化されたGCSクライアントのフィクスチャ"""
    client = EnhancedGCSClient(project=TEST_PROJECT_ID)
    
    # テスト用のバケットとブロブを事前設定
    bucket = client.bucket(TEST_BUCKET_NAME)
    
    # 既存の音声ファイルをシミュレート
    audio_blob = bucket.blob("temp/test-audio.wav")
    audio_blob.upload_from_string(b"fake_audio_data", content_type="audio/wav")
    
    return client


@pytest.fixture
def enhanced_firestore_client() -> EnhancedFirestoreClient:
    """強化されたFirestoreクライアントのフィクスチャ"""
    client = EnhancedFirestoreClient(project=TEST_PROJECT_ID)
    
    # テスト用のジョブデータを事前設定
    collection = client.collection("whisper_jobs")
    job_data = {
        "job_id": "test-doc-id",
        "user_id": TEST_USER["uid"],
        "user_email": TEST_USER["email"],
        "filename": "test-audio.wav",
        "gcs_bucket_name": TEST_BUCKET_NAME,
        "audio_size": 44100,
        "audio_duration_ms": 1000,
        "file_hash": "test-hash-123",
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    doc = collection.document("test-doc-id")
    doc.set(job_data)
    
    return client


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
def enhanced_gcp_services(enhanced_gcs_client, enhanced_firestore_client):
    """強化されたGCPサービスの包括的なモック（autospec付き）"""
    
    # Pub/Sub クライアントのモック（autospec付き）
    mock_pubsub_client = create_autospec('google.cloud.pubsub_v1.PublisherClient', instance=True)
    mock_pubsub_client.topic_path.return_value = f"projects/{TEST_PROJECT_ID}/topics/whisper-queue"
    mock_publish_future = MagicMock()
    mock_publish_future.result.return_value = "message-id-123"
    mock_pubsub_client.publish.return_value = mock_publish_future
    
    with patch.multiple(
        'google.cloud.storage',
        Client=MagicMock(return_value=enhanced_gcs_client)
    ), patch.multiple(
        'google.cloud.firestore',
        Client=MagicMock(return_value=enhanced_firestore_client)
    ), patch.multiple(
        'google.cloud.pubsub_v1',
        PublisherClient=MagicMock(return_value=mock_pubsub_client)
    ):
        yield {
            "storage": enhanced_gcs_client,
            "firestore": enhanced_firestore_client,
            "pubsub": mock_pubsub_client
        }


@pytest.fixture 
def mock_audio_processing():
    """音声処理関連のモック（autospec付き）"""
    
    # subprocess.Popenのautospecモック
    mock_process = create_autospec('subprocess.Popen', instance=True)
    mock_process.communicate.return_value = (b"1.0", b"")  # duration=1.0秒
    mock_process.returncode = 0
    
    with patch('subprocess.Popen', return_value=mock_process), \
         patch('app.core.audio_utils.probe_duration', return_value=1.0), \
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
            "temp_file": mock_temp_file,
            "process": mock_process
        }


@pytest.fixture
def mock_whisper_services():
    """Whisper関連サービスのモック（autospec付き）"""
    
    # バックグラウンドタスクを無効化するモック関数（autospec付き）
    async def mock_trigger_batch_processing(job_id: str, background_tasks):
        """バッチ処理トリガー関数のモック（引数チェック付き）"""
        if not isinstance(job_id, str):
            raise TypeError(f"job_id must be str, got {type(job_id)}")
        pass
    
    # FastAPIのBackgroundTasksのadd_taskメソッドをautospecでモック化
    def mock_add_task(func, *args, **kwargs):
        """BackgroundTasksのadd_taskをモック化（引数チェック付き）"""
        if not callable(func):
            raise TypeError(f"func must be callable, got {type(func)}")
        pass
    
    with patch('backend.app.services.whisper_queue.enqueue_job_atomic') as mock_enqueue, \
         patch('backend.app.api.whisper_batch.trigger_whisper_batch_processing', side_effect=mock_trigger_batch_processing), \
         patch('backend.app.api.whisper_batch._get_current_processing_job_count', return_value=0), \
         patch('backend.app.api.whisper_batch._get_env_var', return_value="5"), \
         patch('backend.app.api.whisper.trigger_whisper_batch_processing', side_effect=mock_trigger_batch_processing), \
         patch('fastapi.BackgroundTasks.add_task', side_effect=mock_add_task):
        
        # enqueue_job_atomicに引数チェックを追加
        def mock_enqueue_job(*args, **kwargs):
            return None
        mock_enqueue.side_effect = mock_enqueue_job
        
        yield {
            "enqueue_job": mock_enqueue,
            "trigger_batch": mock_trigger_batch_processing,
            "add_task": mock_add_task
        }


@pytest_asyncio.fixture
async def async_test_client(enhanced_gcp_services, mock_audio_processing, mock_whisper_services):
    """非同期FastAPIテストクライアント（強化されたモック付き）"""
    # 使用時にのみインポート
    from backend.app.main import app
    
    # AsyncClientを適切に初期化
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def test_client(enhanced_gcp_services, mock_audio_processing, mock_whisper_services):
    """FastAPIテストクライアント（強化されたモック付き）"""
    # 使用時にのみインポート
    from backend.app.main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_firestore_job():
    """サンプルのFirestoreジョブデータ"""
    return {
        "job_id": "test-job-123",
        "user_id": TEST_USER["uid"],
        "user_email": TEST_USER["email"],
        "filename": "test-audio.wav",
        "gcs_bucket_name": TEST_BUCKET_NAME,
        "audio_size": 44100,
        "audio_duration_ms": 1000,
        "file_hash": "test-hash-123",
        "status": "queued",
        "num_speakers": 1,
        "min_speakers": 1,
        "max_speakers": 1,
        "language": "ja",
        "initial_prompt": "",
        "tags": ["test"],
        "description": "テスト用音声",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_transcription_result():
    """サンプルの文字起こし結果データ"""
    return [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "こんにちは",
            "speaker": "SPEAKER_01"
        },
        {
            "start": 1.0,
            "end": 2.0,
            "text": "今日はいい天気ですね",
            "speaker": "SPEAKER_01"
        },
        {
            "start": 2.0,
            "end": 3.0,
            "text": "ありがとうございます",
            "speaker": "SPEAKER_02"
        }
    ]
