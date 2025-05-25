#%% tests/app/firebase_t.py

import os
import sys
import argparse
import random
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.cloud import firestore

# firebase-admin SDKもインポート
try:
    import firebase_admin
    from firebase_admin import credentials, firestore as admin_firestore
    FIREBASE_ADMIN_AVAILABLE = True
except ImportError:
    FIREBASE_ADMIN_AVAILABLE = False
    print("firebase-admin not installed. Using only google-cloud-firestore.")
    
# common_utilsのクラス型をインポート
try:
    from common_utils.class_types import WhisperFirestoreData
    TYPES_AVAILABLE = True
except ImportError:
    TYPES_AVAILABLE = False
    print("common_utils.class_types not available. Using dictionary for sample data.")

def load_environment():
    """
    whisper_queue/config/.env と
    whisper_queue/config_develop/.env.develop の順に環境変数を読み込みます。
    GOOGLE_APPLICATION_CREDENTIALS が相対パスなら絶対パスに変換します。
    """
    root = Path(__file__).resolve().parent.parent.parent

    # 1. 本番／共通用 .env
    env_prod = root / "whisper_queue" / "config" / ".env"
    if env_prod.exists():
        load_dotenv(env_prod)
        print(f"Loaded environment from {env_prod}")

    # 2. 開発用 .env.develop （存在すれば上書きロード）
    env_dev = root / "whisper_queue" / "config_develop" / ".env.develop"
    if env_dev.exists():
        load_dotenv(env_dev)
        print(f"Loaded environment from {env_dev}")

    # 認証情報パスを絶対パスに
    cred = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if cred and not os.path.isabs(cred):
        # .env や .env.develop に書かれた相対パスを解決
        creds_path = root / "whisper_queue" / cred
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)
        print(f"Using credentials at: {os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")
    else:
        print(f"Credentials path: {cred}")

def initialize_firestore():
    """Firestoreクライアントを初期化して返す"""
    project_id = os.environ.get('GCP_PROJECT_ID', 'supportaisystem20250412')
    print(f"Initializing Firestore client with project ID: {project_id}")
    
    # firebase-adminが利用可能ならそれを使う
    if FIREBASE_ADMIN_AVAILABLE:
        try:
            print("Trying to initialize with firebase-admin SDK...")
            cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            print(f"Using credential file: {cred_path}")
            
            # 既存のアプリがあれば削除
            try:
                firebase_admin.delete_app(firebase_admin.get_app())
                print("Deleted existing Firebase app")
            except ValueError:
                pass  # アプリがまだ初期化されていない
            
            # 認証情報を初期化
            cred = credentials.Certificate(cred_path)
            firebase_app = firebase_admin.initialize_app(cred, {
                'projectId': project_id,
            })
            print(f"Firebase app initialized: {firebase_app.name}")
            
            # Firestoreクライアントを取得
            db = admin_firestore.client()
            print("Firebase-admin Firestore client initialized successfully")
            return db
        except Exception as firebase_error:
            print(f"Failed to initialize with firebase-admin: {firebase_error}")
            print("Falling back to google-cloud-firestore...")
    
    # google-cloud-firestoreを使用
    try:
        db = firestore.Client(project=project_id, database='(default)')
        print("Google-cloud-firestore client initialized successfully")
        return db
    except Exception as e:
        print(f"Failed to initialize Firestore client: {e}")
        return None

def clear_collection(db, collection_name, batch_size=50):
    """コレクションのすべてのドキュメントを削除する"""
    print(f"Clearing collection: {collection_name}")
    coll_ref = db.collection(collection_name)
    
    # ドキュメントを少しずつ削除
    deleted = 0
    docs = list(coll_ref.limit(batch_size).stream())
    while docs:
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            deleted += 1
        
        # バッチコミット
        batch.commit()
        print(f"Deleted {deleted} documents...")
        
        # 次のバッチを取得
        docs = list(coll_ref.limit(batch_size).stream())
    
    print(f"Finished clearing collection {collection_name} - {deleted} documents deleted")
    return deleted

def create_test_data(db, collection_name, config=None):
    """テスト用のサンプルデータを作成して追加する
    
    Args:
        db: Firestoreクライアント
        collection_name: コレクション名
        config: データ生成設定 (辞書) 例: {'queued': 5, 'processing': 2, 'completed': 3, 'failed': 2}
    """
    if config is None:
        # デフォルト設定
        config = {'queued': 5, 'processing': 2, 'completed': 3, 'failed': 2, 'canceled': 1}
    
    print(f"Creating test samples in collection {collection_name} with config: {config}")
    
    # バッチ処理の準備
    batch = db.batch()
    created = 0
    total = sum(config.values())
    
    # 現在の時刻を基準に、作成日時をずらすためのリスト
    # 古いものから新しいものまで、時間差をつける
    base_time = datetime.now() - timedelta(hours=24)  # 24時間前から開始
    
    # 各ステータスごとにデータを作成
    for status, count in config.items():
        print(f"Creating {count} samples with status '{status}'...")
        
        for i in range(count):
            # インデックスを計算（各ステータス内で連番、全体でも連番）
            status_idx = i + 1
            global_idx = created + 1
            
            # タイムスタンプを計算（古いものから新しいものへ）
            # 0-23時間前までのタイムスタンプを作成し、同じステータスなら新しいものが先に処理されるよう調整
            time_offset = (total - global_idx) / total * 24
            created_time = base_time + timedelta(hours=time_offset)
            
            # ジョブIDを生成（分かりやすくするためにステータスを含める）
            job_id = f"test-{status}-{status_idx}-{created_time.strftime('%Y%m%d%H%M%S')}"
            
            # 基本データを準備
            base_data = {
                "job_id": job_id,
                "user_id": f"test-user-{global_idx}",
                "user_email": f"test-user-{global_idx}@example.com",
                "filename": f"test_audio_{status}_{status_idx}.mp3",
                "description": f"テスト用音声ファイル（{status}）",
                "recording_date": created_time.strftime("%Y-%m-%d"),
                "gcs_backet_name": "test-bucket",
                "audio_file_path": f"audio/test_{status}_{status_idx}.mp3",
                "transcription_file_path": f"transcriptions/test_{status}_{status_idx}.json",
                "audio_size": 1024000 + (global_idx * 100000),  # サイズを少しずつ変える
                "audio_duration": 60 + (global_idx * 30),  # 長さも少しずつ変える
                "file_hash": f"hash-{job_id}",
                "language": "ja",
                "initial_prompt": f"これはステータス「{status}」のテスト用音声です",
                "status": status,
                "tags": [f"tag{global_idx}", status, "test"],
            }
            
            # ステータスに応じた追加データ
            if status == "processing":
                # 処理中なら開始時刻も設定
                base_data["process_started_at"] = created_time + timedelta(minutes=random.randint(5, 30))
            elif status in ["completed", "failed", "canceled"]:
                # 完了系なら開始・終了時刻も設定
                start_time = created_time + timedelta(minutes=random.randint(5, 30))
                base_data["process_started_at"] = start_time
                base_data["process_ended_at"] = start_time + timedelta(minutes=random.randint(2, 15))
                
                # 失敗の場合はエラーメッセージも
                if status == "failed":
                    base_data["error_message"] = random.choice([
                        "音声ファイルの形式が不正です",
                        "処理がタイムアウトしました",
                        "音声認識エンジンでエラーが発生しました",
                        "GPUリソースが不足しています",
                        "バッチジョブの起動に失敗しました"
                    ])
            
            # データを準備
            if TYPES_AVAILABLE:
                # 日時フィールドはサーバータイムスタンプを使いたいので一旦除外
                data_fields = {k: v for k, v in base_data.items() 
                              if k not in ['created_at', 'updated_at']}
                job_data = WhisperFirestoreData(**data_fields)
                data = job_data.model_dump()
                
                # タイムスタンプフィールドを設定
                if "process_started_at" in base_data:
                    data["process_started_at"] = base_data["process_started_at"]
                if "process_ended_at" in base_data:
                    data["process_ended_at"] = base_data["process_ended_at"]
            else:
                # 直接辞書を使用
                data = base_data.copy()
            
            # 作成日時とデータの更新日時を設定
            data['created_at'] = created_time
            
            # エラーが発生する部分を修正
            # NoneとDatetimeの比較を避けるため、必ずdatetimeオブジェクトを使用
            process_started = data.get('process_started_at')
            process_started = process_started if isinstance(process_started, datetime) else created_time
            
            process_ended = data.get('process_ended_at')
            process_ended = process_ended if isinstance(process_ended, datetime) else created_time
            
            # 常にdatetimeオブジェクト同士を比較
            data['updated_at'] = max(created_time, process_started, process_ended)
            
            # バッチに追加
            doc_ref = db.collection(collection_name).document(job_id)
            batch.set(doc_ref, data)
            created += 1
            
            # 20ドキュメントごとにコミット
            if created % 20 == 0:
                batch.commit()
                print(f"Created {created}/{total} documents...")
                batch = db.batch()
    
    # 残りのドキュメントをコミット
    if created % 20 != 0:
        batch.commit()
    
    print(f"Finished creating {created} test documents in collection {collection_name}")
    return created

def list_collections(db):
    """コレクション一覧とそのドキュメントを表示"""
    print("\n=== Collections List ===")
    try:
        collections = list(db.collections())
        print(f"Found {len(collections)} collections:")
        for col in collections:
            print(f"- Collection: `{col.id}`")
            # 各コレクションのドキュメント数を取得
            docs_count = len(list(col.limit(100).stream()))
            print(f"  → {docs_count}+ documents")
    except Exception as e:
        print(f"Error listing collections: {e}")

def list_collection_docs(db, collection_name, limit=20):
    """特定のコレクションのドキュメントを表示"""
    print(f"\n=== Documents in Collection '{collection_name}' ===")
    try:
        # ステータスごとのカウント
        status_count = {}
        
        # ステータスごとに集計
        for status in ['queued', 'processing', 'completed', 'failed', 'canceled']:
            query = db.collection(collection_name).where('status', '==', status)
            count_docs = len(list(query.limit(1000).stream()))
            status_count[status] = count_docs
        
        print("ステータス別集計:")
        for status, count in status_count.items():
            print(f"  {status}: {count}件")
        
        print("\n最新のドキュメント一覧:")
        docs = list(db.collection(collection_name).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).stream())
        print(f"Found {len(docs)} documents (limit: {limit}):")
        
        for doc in docs:
            data = doc.to_dict()
            created_at = data.get('created_at')
            if hasattr(created_at, 'strftime'):
                created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')
                
            print(f"- Document ID: {doc.id}")
            print(f"  Status: {data.get('status', 'unknown')}")
            print(f"  User: {data.get('user_email', 'unknown')}")
            print(f"  Filename: {data.get('filename', 'unknown')}")
            print(f"  Created: {created_at}")
            if data.get('error_message'):
                print(f"  Error: {data.get('error_message')}")
            print()
            
    except Exception as e:
        print(f"Error listing documents: {e}")

def parse_args():
    """コマンドライン引数のパース"""
    parser = argparse.ArgumentParser(description='Firebase操作ツール')
    parser.add_argument('--action', '-a', choices=['list', 'clear', 'create', 'all'], 
                        default='list', help='実行アクション (list=一覧表示, clear=コレクションクリア, create=テストデータ作成, all=すべて)')
    parser.add_argument('--collection', '-c', default='whisper_jobs', 
                        help='操作対象のコレクション名 (デフォルト: whisper_jobs)')
    
    # 各ステータスのサンプル数を指定するオプション
    parser.add_argument('--queued', type=int, default=5, help='queued状態のサンプル数 (デフォルト: 5)')
    parser.add_argument('--processing', type=int, default=2, help='processing状態のサンプル数 (デフォルト: 2)')
    parser.add_argument('--completed', type=int, default=3, help='completed状態のサンプル数 (デフォルト: 3)')
    parser.add_argument('--failed', type=int, default=2, help='failed状態のサンプル数 (デフォルト: 2)')
    parser.add_argument('--canceled', type=int, default=1, help='canceled状態のサンプル数 (デフォルト: 1)')
    
    return parser.parse_args()

def main():
    # コマンドライン引数を解析
    args = parse_args()
    
    # 環境変数読み込み
    load_environment()

    # Firestoreクライアント初期化
    db = initialize_firestore()
    if not db:
        print("Firestore client initialization failed. Exiting.")
        return 1
    
    # 環境変数から取得するか、コマンドライン引数を使用
    collection_name = args.collection
    if not collection_name:
        collection_name = os.environ.get("WHISPER_JOBS_COLLECTION", "whisper_jobs")
    
    # サンプル設定
    sample_config = {
        'queued': args.queued,
        'processing': args.processing,
        'completed': args.completed,
        'failed': args.failed,
        'canceled': args.canceled
    }
    
    # アクションに応じた処理
    if args.action in ['list', 'all']:
        list_collections(db)
        list_collection_docs(db, collection_name)
    
    if args.action in ['clear', 'all']:
        clear_collection(db, collection_name)
    
    if args.action in ['create', 'all']:
        create_test_data(db, collection_name, sample_config)
        # 作成後に一覧を表示
        list_collection_docs(db, collection_name)
    
    return 0

#%%
if __name__ == "__main__":
    sys.exit(main())
#%%