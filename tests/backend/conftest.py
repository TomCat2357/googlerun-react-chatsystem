"""
統合テスト設定 - バックエンドテスト用

軽量なモック環境と実際のエミュレータ環境の両方をサポート
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import json
import uuid
import sys
import socket
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Generator, AsyncGenerator, Optional
from unittest.mock import Mock, patch, MagicMock

import numpy as np
from pydub import AudioSegment
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# ログ設定
import logging
logger = logging.getLogger(__name__)


# ==============================================================================
# Heavy Module Mocking (最初に実行)
# ==============================================================================

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
    
    # Vertex AI関連のモック
    mock_vertexai = MagicMock()
    mock_vertexai.init = MagicMock()
    mock_generative_models = MagicMock()
    sys.modules['vertexai'] = mock_vertexai
    sys.modules['vertexai.generative_models'] = mock_generative_models
    
    # Speech-to-Text関連のモック
    mock_speech = MagicMock()
    sys.modules['google.cloud.speech'] = mock_speech

# モック初期化を実行
mock_heavy_modules()


# ==============================================================================
# Emulator Availability Check
# ==============================================================================

def check_emulator_availability():
    """エミュレータの利用可能性をチェック"""
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
            availability["firestore_reason"] = f"Firestoreエミュレータチェック中にエラー: {str(e)}"
    
    # GCS エミュレータチェック
    if not shutil.which('docker'):
        availability["gcs_reason"] = "dockerコマンドが見つかりません"
    elif not os.environ.get('STORAGE_EMULATOR_HOST'):
        availability["gcs_reason"] = "STORAGE_EMULATOR_HOST環境変数が設定されていません"
    else:
        try:
            import urllib.request
            gcs_host = os.environ.get('STORAGE_EMULATOR_HOST', 'http://localhost:9000')
            response = urllib.request.urlopen(f"{gcs_host}/_internal/healthcheck", timeout=2)
            if response.status == 200:
                availability["gcs"] = True
            else:
                availability["gcs_reason"] = f"GCSエミュレータのヘルスチェックが失敗: {response.status}"
        except Exception as e:
            availability["gcs_reason"] = f"GCSエミュレータチェック中にエラー: {str(e)}"
    
    return availability


# ==============================================================================
# Pytest Configuration
# ==============================================================================

def pytest_configure(config):
    """pytest設定の初期化"""
    # カスタムマーカーの登録
    config.addinivalue_line(
        "markers", "emulator: tests that require GCP emulators"
    )
    config.addinivalue_line(
        "markers", "performance: performance tests"
    )
    config.addinivalue_line(
        "markers", "error_scenarios: error scenario tests"
    )
    config.addinivalue_line(
        "markers", "integration: integration tests"
    )
    config.addinivalue_line(
        "markers", "slow: slow running tests"
    )


def pytest_collection_modifyitems(config, items):
    """テスト実行時の設定変更"""
    emulator_availability = check_emulator_availability()
    
    for item in items:
        # エミュレータが利用できない場合はスキップ
        if "emulator" in item.keywords:
            if not emulator_availability["firestore"] and not emulator_availability["gcs"]:
                skip_reason = f"エミュレータが利用できません: Firestore({emulator_availability['firestore_reason']}) GCS({emulator_availability['gcs_reason']})"
                item.add_marker(pytest.mark.skip(reason=skip_reason))
        
        # 低速テストに警告マーク
        if "slow" in item.keywords:
            item.add_marker(pytest.mark.filterwarnings("ignore::UserWarning"))


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def emulator_availability():
    """エミュレータ利用可能性情報"""
    return check_emulator_availability()


@pytest.fixture
def test_audio_data():
    """テスト用音声データ"""
    # 1秒間の440Hz正弦波を生成
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio_data = np.sin(2 * np.pi * frequency * t) * 0.5
    return (audio_data * 32767).astype(np.int16)


@pytest.fixture
def temp_audio_file(test_audio_data):
    """一時的な音声ファイル"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        # pydubでWAVファイルを作成
        audio_segment = AudioSegment(
            test_audio_data.tobytes(),
            frame_rate=16000,
            sample_width=2,
            channels=1
        )
        audio_segment.export(temp_file.name, format="wav")
        
        yield temp_file.name
        
        # クリーンアップ
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


@pytest.fixture
def mock_firestore_client():
    """モック化されたFirestoreクライアント"""
    with patch('google.cloud.firestore.Client') as mock_client:
        yield mock_client


@pytest.fixture
def mock_gcs_client():
    """モック化されたGCSクライアント"""
    with patch('google.cloud.storage.Client') as mock_client:
        yield mock_client


@pytest.fixture
def fastapi_test_client():
    """FastAPIテストクライアント"""
    from backend.app.main import app
    return TestClient(app)


@pytest.fixture
async def async_test_client():
    """非同期FastAPIテストクライアント"""
    from backend.app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ==============================================================================
# Emulator-specific Fixtures (条件付きで利用可能)
# ==============================================================================

@pytest.fixture
@pytest.mark.emulator
def real_firestore_client(emulator_availability):
    """実際のFirestoreエミュレータクライアント"""
    if not emulator_availability["firestore"]:
        pytest.skip(f"Firestoreエミュレータが利用できません: {emulator_availability['firestore_reason']}")
    
    # エミュレータ用の環境設定
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    
    # 実際のライブラリをインポート（モックを迂回）
    import importlib
    if 'google.cloud.firestore' in sys.modules:
        importlib.reload(sys.modules['google.cloud.firestore'])
    
    import google.cloud.firestore as firestore
    client = firestore.Client(project="test-project")
    
    yield client
    
    # テスト後のクリーンアップ
    try:
        # テストデータの削除
        collections = client.collections()
        for collection in collections:
            docs = collection.list_documents()
            for doc in docs:
                doc.delete()
    except Exception as e:
        logger.warning(f"Firestoreクリーンアップ中にエラー: {e}")


@pytest.fixture
@pytest.mark.emulator
def real_gcs_client(emulator_availability):
    """実際のGCSエミュレータクライアント"""
    if not emulator_availability["gcs"]:
        pytest.skip(f"GCSエミュレータが利用できません: {emulator_availability['gcs_reason']}")
    
    # エミュレータ用の環境設定
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    
    # 実際のライブラリをインポート（モックを迂回）
    import importlib
    if 'google.cloud.storage' in sys.modules:
        importlib.reload(sys.modules['google.cloud.storage'])
    
    import google.cloud.storage as storage
    client = storage.Client(project="test-project")
    
    yield client
    
    # テスト後のクリーンアップ
    try:
        # テストバケットの削除
        for bucket in client.list_buckets():
            if bucket.name.startswith("test-"):
                bucket.delete(force=True)
    except Exception as e:
        logger.warning(f"GCSクリーンアップ中にエラー: {e}")
