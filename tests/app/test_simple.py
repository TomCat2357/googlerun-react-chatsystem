"""
シンプルなテスト（依存関係のないテスト）
"""

import pytest
import os
from unittest.mock import patch, Mock


def test_environment_variables():
    """環境変数が正しく設定されていることを確認"""
    assert os.environ.get("GCP_PROJECT_ID") == "test-whisper-project"
    assert os.environ.get("GCS_BUCKET_NAME") == "test-whisper-bucket"


def test_basic_math():
    """基本的な計算テスト"""
    assert 1 + 1 == 2
    assert 2 * 3 == 6


@pytest.mark.asyncio
async def test_async_function():
    """非同期関数の基本テスト"""
    async def example_async():
        return "hello"
    
    result = await example_async()
    assert result == "hello"


class TestBasicClass:
    """基本的なクラステスト"""
    
    def test_class_method(self):
        """クラスメソッドのテスト"""
        assert True
    
    @pytest.mark.asyncio
    async def test_async_class_method(self):
        """非同期クラスメソッドのテスト"""
        assert True


def test_mock_basic():
    """基本的なモックテスト"""
    mock_obj = Mock()
    mock_obj.method.return_value = "mocked"
    
    assert mock_obj.method() == "mocked"


@patch('os.path.exists')
def test_patch_decorator(mock_exists):
    """patchデコレータのテスト"""
    mock_exists.return_value = True
    
    assert os.path.exists("/fake/path") is True
