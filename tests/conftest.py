"""
テスト用の共通設定とフィクスチャを提供するconftest.py

このファイルはpytestによって自動的に認識され、すべてのテストで利用可能な
共有リソースや設定を提供します。
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# プロジェクトルートへのパスを追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope="session")
def set_test_environment():
    """テスト環境変数を設定するフィクスチャ"""
    # 元の環境変数を保存
    old_environ = os.environ.copy()
    
    # テスト用の共通環境変数を設定
    os.environ["TESTING"] = "True"
    os.environ["DEBUG"] = "True"
    
    yield
    
    # テスト後に元の環境変数に戻す
    os.environ.clear()
    os.environ.update(old_environ)
