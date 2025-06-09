"""
シンプルなエミュレータテスト（デバッグ用）
"""

import pytest
import os

def test_env_check():
    """環境変数の確認"""
    firestore_host = os.environ.get('FIRESTORE_EMULATOR_HOST')
    storage_host = os.environ.get('STORAGE_EMULATOR_HOST')
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
    
    print(f"FIRESTORE_EMULATOR_HOST: {firestore_host}")
    print(f"STORAGE_EMULATOR_HOST: {storage_host}")
    print(f"GOOGLE_CLOUD_PROJECT: {project_id}")
    
    assert firestore_host is not None, "FIRESTORE_EMULATOR_HOST not set"
    assert storage_host is not None, "STORAGE_EMULATOR_HOST not set"
    assert project_id is not None, "GOOGLE_CLOUD_PROJECT not set"


def test_direct_firestore():
    """直接Firestoreテスト"""
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        pytest.skip("Firestore emulator not available")
    
    try:
        from google.cloud import firestore
        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-project')
        client = firestore.Client(project=project_id)
        
        # シンプルな操作
        collection = client.collection('test_collection')
        doc_ref = collection.document('test_doc')
        doc_ref.set({'simple': 'test', 'value': 123})
        
        # 読み取り
        doc = doc_ref.get()
        assert doc.exists
        data = doc.to_dict()
        assert data['simple'] == 'test'
        assert data['value'] == 123
        
        # 削除
        doc_ref.delete()
        
        print("✅ 直接Firestoreテスト成功")
        
    except Exception as e:
        pytest.fail(f"Direct Firestore test failed: {e}")


def test_direct_gcs():
    """直接GCSテスト"""
    if not os.environ.get('STORAGE_EMULATOR_HOST'):
        pytest.skip("GCS emulator not available")
    
    try:
        from google.cloud import storage
        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-project')
        client = storage.Client(project=project_id)
        
        # バケット作成
        bucket_name = 'test-simple-bucket'
        try:
            bucket = client.bucket(bucket_name)
            bucket.create()
        except Exception:
            bucket = client.bucket(bucket_name)
        
        # ファイル操作
        blob = bucket.blob('test_file.txt')
        test_content = 'simple test content'
        blob.upload_from_string(test_content)
        
        # 読み取り
        downloaded = blob.download_as_text()
        assert downloaded == test_content
        
        # 削除
        blob.delete()
        
        print("✅ 直接GCSテスト成功")
        
    except Exception as e:
        pytest.fail(f"Direct GCS test failed: {e}")