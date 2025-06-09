#!/usr/bin/env python3
"""
GCPエミュレータ 直接テスト実行スクリプト

pytest のフィクスチャやモックを回避して、エミュレータの実際の動作を検証
"""

import os
import json
from datetime import datetime
from google.cloud import firestore, storage


def test_firestore_operations():
    """Firestore エミュレータの動作テスト"""
    print("\n🔸 Firestore 操作テスト開始")
    
    try:
        # クライアント初期化
        db = firestore.Client(project='test-emulator-project')
        
        # Create - データ作成
        test_data = {
            'jobId': 'direct-test-001',
            'userId': 'direct-user',
            'status': 'queued',
            'filename': 'direct-test.wav',
            'language': 'ja',
            'createdAt': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = db.collection('direct_test_jobs').document('direct-test-001')
        doc_ref.set(test_data)
        print("✅ データ作成成功")
        
        # Read - データ読み取り
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data['jobId'] == 'direct-test-001':
                print("✅ データ読み取り成功")
            else:
                print(f"❌ データ内容不一致: {data['jobId']}")
        else:
            print("❌ ドキュメントが存在しません")
            return False
        
        # Update - データ更新
        doc_ref.update({
            'status': 'completed',
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        
        updated_doc = doc_ref.get()
        updated_data = updated_doc.to_dict()
        if updated_data['status'] == 'completed':
            print("✅ データ更新成功")
        else:
            print(f"❌ 更新失敗: {updated_data['status']}")
            return False
        
        # Query - クエリテスト
        queried_docs = list(db.collection('direct_test_jobs').where('status', '==', 'completed').stream())
        if len(queried_docs) >= 1:
            print("✅ クエリ実行成功")
        else:
            print(f"❌ クエリ結果が不正: {len(queried_docs)}件")
            return False
        
        # Delete - データ削除
        doc_ref.delete()
        deleted_doc = doc_ref.get()
        if not deleted_doc.exists:
            print("✅ データ削除成功")
        else:
            print("❌ データ削除失敗")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Firestore エラー: {e}")
        return False


def test_gcs_operations():
    """GCS エミュレータの動作テスト"""
    print("\n🔸 GCS 操作テスト開始")
    
    try:
        # クライアント初期化
        client = storage.Client(project='test-emulator-project')
        bucket_name = 'direct-test-bucket'
        
        # バケット作成
        try:
            bucket = client.bucket(bucket_name)
            bucket.create()
            print("✅ バケット作成成功")
        except Exception:
            bucket = client.bucket(bucket_name)
            print("⚠️ バケット既存（正常）")
        
        # ファイルアップロード
        test_content = "直接テスト用コンテンツ\\n日本語テスト"
        blob = bucket.blob('direct-test/sample.txt')
        blob.upload_from_string(test_content, content_type='text/plain; charset=utf-8')
        print("✅ ファイルアップロード成功")
        
        # ファイル存在確認
        if blob.exists():
            print("✅ ファイル存在確認成功")
        else:
            print("❌ ファイルが存在しません")
            return False
        
        # ファイルダウンロード
        downloaded_content = blob.download_as_text()
        if downloaded_content == test_content:
            print("✅ ファイルダウンロード・検証成功")
        else:
            print(f"❌ ダウンロード内容不一致: {downloaded_content}")
            return False
        
        # JSONファイルテスト
        json_data = {
            'test': True,
            'message': '直接テストJSONファイル',
            'timestamp': datetime.now().isoformat(),
            'items': ['item1', 'item2', 'item3']
        }
        
        json_blob = bucket.blob('direct-test/data.json')
        json_blob.upload_from_string(
            json.dumps(json_data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        print("✅ JSONファイルアップロード成功")
        
        # JSONダウンロード・パース
        downloaded_json_str = json_blob.download_as_text()
        downloaded_json = json.loads(downloaded_json_str)
        
        if (downloaded_json['test'] is True and 
            downloaded_json['message'] == '直接テストJSONファイル' and
            len(downloaded_json['items']) == 3):
            print("✅ JSONファイル検証成功")
        else:
            print(f"❌ JSON内容検証失敗: {downloaded_json}")
            return False
        
        # メタデータテスト
        metadata = {
            'author': 'Direct Test',
            'purpose': 'Emulator Verification',
            'version': '1.0'
        }
        blob.metadata = metadata
        blob.patch()
        print("✅ メタデータ設定成功")
        
        # メタデータ確認
        blob.reload()
        if (blob.metadata and 
            blob.metadata.get('author') == 'Direct Test' and
            blob.metadata.get('purpose') == 'Emulator Verification'):
            print("✅ メタデータ確認成功")
        else:
            print(f"❌ メタデータ確認失敗: {blob.metadata}")
            return False
        
        # ファイル一覧
        blobs = list(bucket.list_blobs(prefix='direct-test/'))
        if len(blobs) >= 2:
            print(f"✅ ファイル一覧取得成功: {len(blobs)}ファイル")
            for b in blobs:
                print(f"   - {b.name} ({b.size} bytes)")
        else:
            print(f"❌ ファイル一覧不正: {len(blobs)}ファイル")
            return False
        
        # クリーンアップ
        for b in blobs:
            b.delete()
        print("✅ テストファイル削除完了")
        
        return True
        
    except Exception as e:
        print(f"❌ GCS エラー: {e}")
        return False


def test_integrated_workflow():
    """統合ワークフローテスト"""
    print("\n🔸 統合ワークフロー テスト開始")
    
    try:
        # 両クライアント初期化
        db = firestore.Client(project='test-emulator-project')
        storage_client = storage.Client(project='test-emulator-project')
        
        bucket_name = 'integrated-workflow-test'
        try:
            bucket = storage_client.bucket(bucket_name)
            bucket.create()
        except Exception:
            bucket = storage_client.bucket(bucket_name)
        
        job_id = 'integrated-workflow-001'
        
        # 1. 音声ファイル模擬アップロード（GCS）
        audio_content = b'RIFF\\x00\\x00\\x00\\x00WAVE' + b'\\x00' * 1000
        audio_path = f'whisper/audio/{job_id}.wav'
        audio_blob = bucket.blob(audio_path)
        audio_blob.metadata = {
            'jobId': job_id,
            'originalName': 'user-recording.wav',
            'uploadedAt': datetime.now().isoformat()
        }
        audio_blob.upload_from_string(audio_content, content_type='audio/wav')
        print("✅ 音声ファイルアップロード完了")
        
        # 2. ジョブデータ作成（Firestore）
        job_data = {
            'jobId': job_id,
            'userId': 'integrated-user',
            'userEmail': 'integrated@example.com',
            'filename': 'user-recording.wav',
            'status': 'queued',
            'gcsBucketName': bucket_name,
            'audioPath': audio_path,
            'audioSize': len(audio_content),
            'language': 'ja',
            'createdAt': firestore.SERVER_TIMESTAMP
        }
        
        job_ref = db.collection('integrated_jobs').document(job_id)
        job_ref.set(job_data)
        print("✅ ジョブデータ作成完了")
        
        # 3. 処理開始（ステータス更新）
        job_ref.update({
            'status': 'processing',
            'processStartedAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        print("✅ 処理開始ステータス更新完了")
        
        # 4. 文字起こし結果保存（GCS）
        transcription_result = {
            'jobId': job_id,
            'segments': [
                {
                    'start': 0.0,
                    'end': 3.5,
                    'text': 'これは統合テストの音声です',
                    'speaker': 'SPEAKER_01'
                },
                {
                    'start': 3.5,
                    'end': 6.8,
                    'text': 'エミュレータが正常に動作しています',
                    'speaker': 'SPEAKER_01'
                }
            ],
            'language': 'ja',
            'duration': 6.8,
            'processingTime': 1.2,
            'speakerCount': 1,
            'createdAt': datetime.now().isoformat()
        }
        
        result_path = f'whisper/results/{job_id}/transcription.json'
        result_blob = bucket.blob(result_path)
        result_blob.upload_from_string(
            json.dumps(transcription_result, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        print("✅ 文字起こし結果保存完了")
        
        # 5. 処理完了（ステータス更新）
        job_ref.update({
            'status': 'completed',
            'resultPath': result_path,
            'processEndedAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        print("✅ 処理完了ステータス更新完了")
        
        # 検証
        # Firestoreデータ確認
        final_job = job_ref.get()
        if final_job.exists:
            final_data = final_job.to_dict()
            if (final_data['status'] == 'completed' and 
                final_data['resultPath'] == result_path):
                print("✅ Firestoreデータ検証成功")
            else:
                print(f"❌ Firestoreデータ検証失敗: {final_data}")
                return False
        else:
            print("❌ 最終ジョブデータが見つかりません")
            return False
        
        # GCSファイル存在確認
        if audio_blob.exists() and result_blob.exists():
            print("✅ GCSファイル存在確認成功")
        else:
            print("❌ GCSファイル存在確認失敗")
            return False
        
        # 結果ファイル内容確認
        result_content = json.loads(result_blob.download_as_text())
        if (result_content['jobId'] == job_id and 
            len(result_content['segments']) == 2 and
            result_content['speakerCount'] == 1):
            print("✅ 結果ファイル内容検証成功")
        else:
            print(f"❌ 結果ファイル内容検証失敗: {result_content}")
            return False
        
        # クリーンアップ
        job_ref.delete()
        audio_blob.delete()
        result_blob.delete()
        print("✅ テストデータクリーンアップ完了")
        
        return True
        
    except Exception as e:
        print(f"❌ 統合ワークフロー エラー: {e}")
        return False


def main():
    """メインテスト実行"""
    print("=" * 50)
    print("GCP エミュレータ 直接動作テスト")
    print("=" * 50)
    
    # 環境変数確認
    firestore_host = os.environ.get('FIRESTORE_EMULATOR_HOST')
    gcs_host = os.environ.get('STORAGE_EMULATOR_HOST')
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'test-emulator-project')
    
    print(f"Firestore Emulator: {firestore_host}")
    print(f"GCS Emulator: {gcs_host}")
    print(f"Project ID: {project_id}")
    
    if not firestore_host:
        print("❌ FIRESTORE_EMULATOR_HOST が設定されていません")
        return False
    
    if not gcs_host:
        print("❌ STORAGE_EMULATOR_HOST が設定されていません")
        return False
    
    # テスト実行
    tests = [
        ("Firestore操作", test_firestore_operations),
        ("GCS操作", test_gcs_operations),
        ("統合ワークフロー", test_integrated_workflow)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                print(f"✅ {test_name}: 成功")
            else:
                print(f"❌ {test_name}: 失敗")
        except Exception as e:
            print(f"❌ {test_name}: 例外発生 - {e}")
            results.append((test_name, False))
    
    # 結果サマリー
    print("\\n" + "=" * 50)
    print("テスト結果サマリー")
    print("=" * 50)
    
    success_count = sum(1 for _, result in results if result)
    total_count = len(results)
    
    for test_name, result in results:
        status = "✅ 成功" if result else "❌ 失敗"
        print(f"{test_name}: {status}")
    
    print(f"\\n総合結果: {success_count}/{total_count} テスト成功")
    
    if success_count == total_count:
        print("🎉 全てのテストが成功しました！")
        print("FirestoreとGCSエミュレータが完全に動作しています。")
        return True
    else:
        print("⚠️ 一部のテストが失敗しました。")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)