#!/usr/bin/env python3
"""
エミュレータ接続の直接テスト
"""

import os
import sys
import json
import socket
import urllib.request

def check_emulator_direct():
    """エミュレータへの直接接続テスト"""
    print("=== エミュレータ接続テスト ===")
    
    # 環境変数の確認
    firestore_host = os.environ.get('FIRESTORE_EMULATOR_HOST')
    storage_host = os.environ.get('STORAGE_EMULATOR_HOST')
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
    
    print(f"FIRESTORE_EMULATOR_HOST: {firestore_host}")
    print(f"STORAGE_EMULATOR_HOST: {storage_host}")
    print(f"GOOGLE_CLOUD_PROJECT: {project_id}")
    print()
    
    # Firestoreエミュレータ接続テスト
    if firestore_host:
        try:
            host, port = firestore_host.split(':')
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, int(port)))
            sock.close()
            
            if result == 0:
                print(f"✅ Firestoreエミュレータ接続成功: {firestore_host}")
                
                # 実際のFirestoreクライアントテスト
                try:
                    from google.cloud import firestore
                    client = firestore.Client(project=project_id)
                    
                    # 接続テスト
                    test_collection = client.collection('connection_test')
                    test_doc = test_collection.document('test')
                    test_doc.set({'test': True, 'connection': 'success'})
                    result = test_doc.get()
                    test_doc.delete()
                    
                    print(f"✅ Firestoreクライアント操作成功: {result.to_dict()}")
                    
                except Exception as e:
                    print(f"❌ Firestoreクライアント操作失敗: {e}")
            else:
                print(f"❌ Firestoreエミュレータ接続失敗: {firestore_host}")
        except Exception as e:
            print(f"❌ Firestoreエミュレータチェックエラー: {e}")
    else:
        print("❌ FIRESTORE_EMULATOR_HOST環境変数が設定されていません")
    
    print()
    
    # GCSエミュレータ接続テスト
    if storage_host:
        try:
            # 健康チェック
            with urllib.request.urlopen(f"{storage_host}/_internal/healthcheck", timeout=2) as response:
                if response.status == 200:
                    print(f"✅ GCSエミュレータ健康チェック成功: {storage_host}")
                    
                    # 実際のGCSクライアントテスト
                    try:
                        from google.cloud import storage
                        client = storage.Client(project=project_id)
                        
                        # バケット作成テスト
                        bucket_name = 'test-connection-bucket'
                        try:
                            bucket = client.bucket(bucket_name)
                            bucket.create()
                        except Exception:
                            bucket = client.bucket(bucket_name)
                        
                        # ファイル操作テスト
                        test_blob = bucket.blob('connection_test.txt')
                        test_blob.upload_from_string('connection test')
                        content = test_blob.download_as_text()
                        test_blob.delete()
                        
                        print(f"✅ GCSクライアント操作成功: content={content}")
                        
                    except Exception as e:
                        print(f"❌ GCSクライアント操作失敗: {e}")
                else:
                    print(f"❌ GCSエミュレータ健康チェック失敗: status {response.status}")
        except Exception as e:
            print(f"❌ GCSエミュレータチェックエラー: {e}")
    else:
        print("❌ STORAGE_EMULATOR_HOST環境変数が設定されていません")

if __name__ == '__main__':
    check_emulator_direct()