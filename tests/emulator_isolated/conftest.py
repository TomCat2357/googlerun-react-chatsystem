"""
エミュレータ専用のconftest.py（モック無し）

このconftest.pyはモック化を一切行わず、実際のGCPライブラリとエミュレータを使用します。
"""

import pytest
import os
import socket
import subprocess
import urllib.request
import tempfile
from typing import Generator, Optional

# ログ設定
import logging
logger = logging.getLogger(__name__)


def check_emulator_availability():
    """エミュレータの利用可能性をチェック"""
    import shutil
    
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
    if not os.environ.get('STORAGE_EMULATOR_HOST'):
        availability["gcs_reason"] = "STORAGE_EMULATOR_HOST環境変数が設定されていません"
    else:
        try:
            # GCSエミュレータ接続確認
            emulator_host = os.environ.get('STORAGE_EMULATOR_HOST', 'http://localhost:9000')
            with urllib.request.urlopen(f"{emulator_host}/_internal/healthcheck", timeout=5) as response:
                if response.status == 200:
                    availability["gcs"] = True
                else:
                    availability["gcs_reason"] = f"GCSエミュレータ健康チェック失敗: status {response.status}"
        except Exception as e:
            availability["gcs_reason"] = f"GCSエミュレータに接続できません: {e}"
    
    return availability


@pytest.fixture(scope="session")
def emulator_availability():
    """エミュレータ利用可能性のセッションスコープチェック"""
    availability = check_emulator_availability()
    
    if not availability["firestore"]:
        pytest.skip(f"Firestore emulator not available: {availability['firestore_reason']}")
    
    if not availability["gcs"]:
        pytest.skip(f"GCS emulator not available: {availability['gcs_reason']}")
    
    return availability


@pytest.fixture
def firestore_client(emulator_availability):
    """Firestoreクライアント（エミュレータ接続）"""
    from google.cloud import firestore
    
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-emulator-project')
    client = firestore.Client(project=project_id)
    
    yield client


@pytest.fixture
def gcs_client(emulator_availability):
    """GCSクライアント（エミュレータ接続）"""
    from google.cloud import storage
    
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-emulator-project')
    client = storage.Client(project=project_id)
    
    yield client


@pytest.fixture
def test_bucket(gcs_client):
    """テスト用バケット"""
    bucket_name = 'test-whisper-emulator-bucket'
    
    try:
        bucket = gcs_client.bucket(bucket_name)
        bucket.create()
    except Exception:
        # バケットが既に存在する場合
        bucket = gcs_client.bucket(bucket_name)
    
    yield bucket
    
    # クリーンアップ
    try:
        blobs = list(bucket.list_blobs())
        for blob in blobs:
            blob.delete()
    except Exception as e:
        logger.warning(f"テストバケットクリーンアップエラー: {e}")


@pytest.fixture
def test_collection(firestore_client):
    """テスト用Firestoreコレクション"""
    collection_name = 'test_whisper_jobs'
    collection = firestore_client.collection(collection_name)
    
    yield collection
    
    # クリーンアップ
    try:
        docs = collection.limit(100).stream()
        for doc in docs:
            doc.reference.delete()
    except Exception as e:
        logger.warning(f"テストコレクションクリーンアップエラー: {e}")


@pytest.fixture
def emulator_environment(firestore_client, gcs_client, test_bucket, test_collection):
    """エミュレータテスト環境のセットアップ"""
    
    class EmulatorTestEnvironment:
        def __init__(self):
            self.firestore_client = firestore_client
            self.gcs_client = gcs_client
            self.test_bucket = test_bucket
            self.test_collection = test_collection
            self.project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-emulator-project')
            
            # SERVER_TIMESTAMP アクセス用
            from google.cloud import firestore
            self.SERVER_TIMESTAMP = firestore.SERVER_TIMESTAMP
            
        def create_test_audio_file(self, file_path: str, content: bytes = None):
            """テスト用音声ファイルをGCSに作成"""
            if content is None:
                # 模擬WAVファイルコンテンツ
                content = b'RIFF' + b'\x00' * 4 + b'WAVE' + b'\x00' * 1000
            
            blob = self.test_bucket.blob(file_path)
            blob.upload_from_string(content, content_type='audio/wav')
            return blob
            
        def create_test_job_document(self, job_id: str, job_data: dict = None):
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
                    'createdAt': self.SERVER_TIMESTAMP,
                    'updatedAt': self.SERVER_TIMESTAMP
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


# pytestマーカー設定
def pytest_configure(config):
    """pytest設定でカスタムマーカーを追加"""
    config.addinivalue_line(
        "markers", "emulator: mark test as emulator integration test (requires running emulators)"
    )


def pytest_collection_modifyitems(config, items):
    """エミュレータが利用できない場合、エミュレータテストをスキップ"""
    emulator_check = check_emulator_availability()
    
    for item in items:
        # エミュレータマーカーのチェック
        if item.get_closest_marker("emulator"):
            missing_emulators = []
            if not emulator_check["firestore"]:
                missing_emulators.append(f"Firestore: {emulator_check['firestore_reason']}")
            if not emulator_check["gcs"]:
                missing_emulators.append(f"GCS: {emulator_check['gcs_reason']}")
            
            if missing_emulators:
                item.add_marker(pytest.mark.skip(reason=f"Emulators not available: {', '.join(missing_emulators)}"))