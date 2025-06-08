"""
Whisperテストシステム改善版のconftest
- 完全なPydanticバリデーション対応データ
- より現実的なモック設定
- エラーハンドリング強化
"""

import pytest
import pytest_asyncio
import os
import json
import uuid
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

import numpy as np
from pydub import AudioSegment
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport


# テスト用設定を基本conftest.pyから継承
from .conftest import TEST_PROJECT_ID, TEST_BUCKET_NAME, TEST_USER, mock_heavy_modules


@pytest.fixture
def complete_whisper_job_data():
    """完全なWhisperジョブデータ（全必須フィールド含む）"""
    return {
        "job_id": f"test-job-{uuid.uuid4()}",
        "user_id": "test-user-123",
        "user_email": "test-user@example.com",           # 必須フィールド
        "filename": "complete-test-audio.wav",           # 必須フィールド
        "gcs_bucket_name": TEST_BUCKET_NAME,             # 必須フィールド
        "audio_size": 1024000,                           # 必須フィールド
        "audio_duration_ms": 60000,                      # 必須フィールド
        "file_hash": f"hash-{uuid.uuid4().hex}",         # 必須フィールド
        "status": "queued",                              # 必須フィールド
        "original_name": "完全テスト音声.wav",
        "description": "完全なバリデーション対応テストデータ",
        "recording_date": "2025-06-08",
        "language": "ja",
        "initial_prompt": "これは日本語のテスト音声です",
        "tags": ["test", "validation", "complete"],
        "num_speakers": 2,
        "min_speakers": 1,
        "max_speakers": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def whisper_upload_request_complete():
    """完全なWhisperアップロードリクエストデータ"""
    return {
        "audio_data": "VGVzdCBhdWRpbyBkYXRhIGVuY29kZWQgaW4gYmFzZTY0",  # 必須
        "filename": "upload-test-audio.wav",                        # 必須
        "gcs_object": "temp/upload-test-audio.wav",
        "original_name": "アップロードテスト音声.wav",
        "description": "完全なアップロードリクエストテスト",
        "recording_date": "2025-06-08",
        "language": "ja",
        "initial_prompt": "日本語の音声ファイルです。専門用語を含む可能性があります。",
        "tags": ["upload", "test", "complete"],
        "num_speakers": 2,
        "min_speakers": 1,
        "max_speakers": 4
    }


@pytest.fixture
def realistic_transcription_data():
    """現実的な文字起こし結果データ"""
    return [
        {
            "start": 0.0,
            "end": 2.5,
            "text": "おはようございます。今日は重要な会議の録音です。",
            "speaker": "SPEAKER_01"
        },
        {
            "start": 2.5,
            "end": 5.8,
            "text": "はい、よろしくお願いします。まず、プロジェクトの進捗状況についてお話しします。",
            "speaker": "SPEAKER_02"
        },
        {
            "start": 5.8,
            "end": 9.2,
            "text": "現在の開発進捗は約75%で、予定より少し遅れていますが、品質は良好です。",
            "speaker": "SPEAKER_02"
        },
        {
            "start": 9.2,
            "end": 11.0,
            "text": "承知しました。次のマイルストーンはいつ頃でしょうか？",
            "speaker": "SPEAKER_01"
        },
        {
            "start": 11.0,
            "end": 14.5,
            "text": "来月の15日を目標としています。テストフェーズも含めて計画しています。",
            "speaker": "SPEAKER_02"
        }
    ]


@pytest.fixture
def realistic_speaker_config():
    """現実的なスピーカー設定データ"""
    return {
        "SPEAKER_01": {
            "name": "田中部長",
            "color": "#FF5722",
            "role": "プロジェクトマネージャー",
            "department": "開発部"
        },
        "SPEAKER_02": {
            "name": "佐藤エンジニア",
            "color": "#2196F3",
            "role": "シニアエンジニア",
            "department": "開発部"
        },
        "SPEAKER_03": {
            "name": "鈴木デザイナー",
            "color": "#4CAF50",
            "role": "UIデザイナー",
            "department": "デザイン部"
        }
    }


@pytest.fixture
def enhanced_audio_file():
    """強化されたテスト用音声ファイル（より現実的）"""
    # より複雑な音声波形を生成（複数の周波数成分）
    sample_rate = 16000
    duration_ms = 3000  # 3秒
    
    # NumPyで複数周波数の音声波形を生成
    t = np.linspace(0, duration_ms / 1000, int(sample_rate * duration_ms / 1000), False)
    
    # 基本周波数 + ハーモニクス
    wave1 = np.sin(2 * np.pi * 440 * t) * 0.3  # A4音
    wave2 = np.sin(2 * np.pi * 880 * t) * 0.2  # A5音
    wave3 = np.sin(2 * np.pi * 220 * t) * 0.15 # A3音
    
    # ノイズを少し追加（現実的な録音状況をシミュレート）
    noise = np.random.normal(0, 0.02, len(t))
    
    # 波形を合成
    combined_wave = wave1 + wave2 + wave3 + noise
    
    # 音量の時間変化を追加（フェードイン・フェードアウト）
    fade_samples = int(sample_rate * 0.1)  # 0.1秒のフェード
    combined_wave[:fade_samples] *= np.linspace(0, 1, fade_samples)
    combined_wave[-fade_samples:] *= np.linspace(1, 0, fade_samples)
    
    # 16bit整数に変換
    audio_data = (combined_wave * 32767).astype(np.int16)
    
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
def enhanced_error_test_cases():
    """強化されたエラーテストケース"""
    return {
        "missing_required_fields": {
            "filename": "test.wav",
            # audio_dataが欠落
            "description": "必須フィールド欠落テスト"
        },
        "invalid_data_types": {
            "audio_data": 12345,  # 文字列でなく数値
            "filename": ["invalid", "array"],  # 配列は無効
            "num_speakers": "invalid_number"  # 文字列は無効
        },
        "boundary_values": {
            "audio_data": "valid_data",
            "filename": "test.wav",
            "num_speakers": 0,  # 境界値：0話者
            "min_speakers": -1,  # 境界値：負の値
            "max_speakers": 1000  # 境界値：非現実的な大きな値
        },
        "large_data": {
            "audio_data": "x" * 200000000,  # 200MB相当の文字列
            "filename": "large_file.wav",
            "description": "x" * 10000  # 10,000文字の説明
        }
    }


@pytest.fixture
def enhanced_gcp_services_with_validation():
    """バリデーション付き強化GCPサービスモック"""
    
    class ValidatedGCSBlob:
        """バリデーション付きGCS Blob"""
        
        def __init__(self, bucket_name: str, blob_name: str):
            self.bucket_name = bucket_name
            self.name = blob_name
            self._content: bytes = b""
            self._content_type: str = "application/octet-stream"
            self._size: int = 0
            self._exists: bool = False
            self._metadata: Dict[str, Any] = {}
        
        def upload_from_string(self, data: bytes, content_type: str = None):
            """文字列からアップロード（バリデーション付き）"""
            if isinstance(data, str):
                data = data.encode('utf-8')
            
            self._content = data
            self._size = len(data)
            self._exists = True
            
            if content_type:
                self._content_type = content_type
                
            # ファイルサイズ制限チェック
            max_size = 100 * 1024 * 1024  # 100MB
            if self._size > max_size:
                raise Exception(f"File too large: {self._size} bytes > {max_size} bytes")
        
        def exists(self) -> bool:
            return self._exists
        
        @property
        def size(self) -> int:
            return self._size
        
        @property
        def content_type(self) -> str:
            return self._content_type
        
        def download_as_text(self) -> str:
            if not self._exists:
                raise Exception("Blob does not exist")
            return self._content.decode('utf-8')
        
        def generate_signed_url(self, expiration: int = 3600, version="v4", method="GET", content_type=None) -> str:
            return f"https://storage.googleapis.com/{self.bucket_name}/{self.name}?signed=true&exp={expiration}"
        
        def reload(self):
            """メタデータの再読み込み"""
            pass
    
    class ValidatedGCSBucket:
        """バリデーション付きGCS Bucket"""
        
        def __init__(self, bucket_name: str):
            self.name = bucket_name
            self._blobs: Dict[str, ValidatedGCSBlob] = {}
        
        def blob(self, blob_name: str) -> ValidatedGCSBlob:
            if blob_name not in self._blobs:
                self._blobs[blob_name] = ValidatedGCSBlob(self.name, blob_name)
            return self._blobs[blob_name]
    
    class ValidatedGCSClient:
        """バリデーション付きGCS Client"""
        
        def __init__(self):
            self._buckets: Dict[str, ValidatedGCSBucket] = {}
        
        def bucket(self, bucket_name: str) -> ValidatedGCSBucket:
            if bucket_name not in self._buckets:
                self._buckets[bucket_name] = ValidatedGCSBucket(bucket_name)
            return self._buckets[bucket_name]
    
    class ValidatedFirestoreDocument:
        """バリデーション付きFirestore Document"""
        
        def __init__(self, doc_id: str):
            self.id = doc_id
            self._data: Dict[str, Any] = {}
            self._exists: bool = False
        
        def set(self, data: Dict[str, Any]):
            """ドキュメント設定（バリデーション付き）"""
            # 基本的なバリデーション
            if not isinstance(data, dict):
                raise ValueError("Data must be a dictionary")
            
            self._data = data.copy()
            self._exists = True
        
        def update(self, data: Dict[str, Any]):
            """ドキュメント更新"""
            if not self._exists:
                raise Exception("Document does not exist")
            
            self._data.update(data)
        
        def get(self):
            """ドキュメント取得"""
            return self
        
        def to_dict(self) -> Dict[str, Any]:
            return self._data.copy()
        
        @property
        def exists(self) -> bool:
            return self._exists
    
    class ValidatedFirestoreCollection:
        """バリデーション付きFirestore Collection"""
        
        def __init__(self, collection_name: str):
            self.name = collection_name
            self._documents: Dict[str, ValidatedFirestoreDocument] = {}
        
        def document(self, doc_id: str) -> ValidatedFirestoreDocument:
            if doc_id not in self._documents:
                self._documents[doc_id] = ValidatedFirestoreDocument(doc_id)
            return self._documents[doc_id]
        
        def where(self, field: str, operator: str, value: Any):
            """クエリ条件"""
            mock_query = Mock()
            
            # フィルタリング結果をシミュレート
            filtered_docs = []
            for doc in self._documents.values():
                if doc.exists and field in doc._data:
                    doc_value = doc._data[field]
                    if operator == "==" and doc_value == value:
                        filtered_docs.append(doc)
                    elif operator == ">=" and doc_value >= value:
                        filtered_docs.append(doc)
                    elif operator == "<=" and doc_value <= value:
                        filtered_docs.append(doc)
            
            mock_query.stream = Mock(return_value=filtered_docs)
            mock_query.limit = Mock(return_value=mock_query)
            mock_query.order_by = Mock(return_value=mock_query)
            
            return mock_query
        
        def stream(self):
            """全ドキュメント取得"""
            return [doc for doc in self._documents.values() if doc.exists]
    
    class ValidatedFirestoreClient:
        """バリデーション付きFirestore Client"""
        
        def __init__(self):
            self._collections: Dict[str, ValidatedFirestoreCollection] = {}
            self.SERVER_TIMESTAMP = "mock_server_timestamp"
        
        def collection(self, collection_name: str) -> ValidatedFirestoreCollection:
            if collection_name not in self._collections:
                self._collections[collection_name] = ValidatedFirestoreCollection(collection_name)
            return self._collections[collection_name]
    
    # サービスインスタンスを作成
    gcs_client = ValidatedGCSClient()
    firestore_client = ValidatedFirestoreClient()
    
    # デフォルトデータを設定
    bucket = gcs_client.bucket(TEST_BUCKET_NAME)
    jobs_collection = firestore_client.collection("whisper_jobs")
    
    # テスト用のデフォルトジョブを作成
    default_job_doc = jobs_collection.document("test-doc-id")
    default_job_doc.set({
        "job_id": "test-doc-id",
        "user_id": "test-user-123",
        "user_email": "test-user@example.com",
        "filename": "test-audio.wav",
        "gcs_bucket_name": TEST_BUCKET_NAME,
        "audio_size": 44100,
        "audio_duration_ms": 1000,
        "file_hash": "test-hash-123",
        "status": "completed",
        "created_at": "2025-06-01T10:00:00Z",
        "updated_at": "2025-06-01T10:05:00Z"
    })
    
    return {
        "storage": gcs_client,
        "firestore": firestore_client
    }


@pytest.fixture
def performance_test_data():
    """パフォーマンステスト用データ"""
    return {
        "concurrent_requests": 5,
        "large_file_size": 50 * 1024 * 1024,  # 50MB
        "memory_threshold": 100 * 1024 * 1024,  # 100MB
        "response_time_threshold": 5.0,  # 5秒
        "batch_processing_jobs": [
            {
                "job_id": f"perf-job-{i}",
                "user_id": "test-user-123",
                "user_email": "test-user@example.com",
                "filename": f"performance-test-{i}.wav",
                "gcs_bucket_name": TEST_BUCKET_NAME,
                "audio_size": 1024000 + i * 100000,
                "audio_duration_ms": 60000 + i * 10000,
                "file_hash": f"perf-hash-{i}",
                "status": "queued"
            }
            for i in range(10)
        ]
    }


@pytest.fixture
def realistic_error_scenarios():
    """現実的なエラーシナリオ"""
    return {
        "network_errors": [
            "Connection timeout",
            "Network unreachable",
            "DNS resolution failed"
        ],
        "gcp_errors": [
            "Insufficient permissions",
            "Quota exceeded",
            "Service unavailable"
        ],
        "validation_errors": [
            "Invalid file format",
            "File size too large",
            "Unsupported audio codec"
        ],
        "processing_errors": [
            "Transcription model not available",
            "Audio quality too poor",
            "Language detection failed"
        ]
    }