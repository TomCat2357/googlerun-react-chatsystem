#%% tests/app/list_firestore.py

import os
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import firestore

# firebase-admin SDKもインポート（これを使うとうまくいく可能性もある）
try:
    import firebase_admin
    from firebase_admin import credentials, firestore as admin_firestore
    FIREBASE_ADMIN_AVAILABLE = True
except ImportError:
    FIREBASE_ADMIN_AVAILABLE = False
    print("firebase-admin not installed. Using only google-cloud-firestore.")

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
def main():
    # 環境変数読み込み
    load_environment()

    # Firestoreクライアント初期化のデバッグ情報
    print(f"Project ID: {os.environ.get('GCP_PROJECT_ID')}")
    print(f"Using credentials: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
    
    # Firestore クライアント初期化
    try:
        # プロジェクトIDを明示的に指定してクライアントを初期化
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
            except Exception as firebase_error:
                print(f"Failed to initialize with firebase-admin: {firebase_error}")
                print("Falling back to google-cloud-firestore...")
                # データベースIDを明示的に指定（デフォルト）
                db = firestore.Client(project=project_id, database='(default)')
                print("Google-cloud-firestore client initialized successfully")
        else:
            # データベースIDを明示的に指定（デフォルト）
            db = firestore.Client(project=project_id, database='(default)')
            print("Google-cloud-firestore client initialized successfully")
    except Exception as e:
        print(f"Failed to initialize Firestore client: {e}")
        return

    # コレクション一覧取得
    try:
        print("Attempting to list collections...")
        collections = list(db.collections())
        print(f"Found {len(collections)} collections:")
        for col in collections:
            print(f"- Collection: `{col.id}`")
            # 各コレクションのドキュメントを取得
            docs = list(col.stream())
            print(f"  → {len(docs)} documents:")
            for doc in docs:
                data = doc.to_dict()
                print(f"    • Document ID: {doc.id}")
                for k, v in data.items():
                    print(f"        {k!r}: {v!r}")
            print()
    except Exception as e:
        print(f"Error listing collections: {e}")
        
    # テスト用のコレクションとドキュメントを作成
    try:
        print("\n--- テスト用コレクションの作成を試みます ---")
        # 複数の異なるコレクション名でテスト
        test_collections = [
            'test_collection', 
            'test_jobs', 
            'test_whisper', 
            'whisper_jobs'
        ]
        
        for coll_name in test_collections:
            try:
                doc_ref = db.collection(coll_name).document('test_document')
                doc_ref.set({
                    'test_field': f'テスト値 for {coll_name}',
                    'job_id': 'test_job',
                    'created_at': firestore.SERVER_TIMESTAMP
                })
                print(f"テストドキュメントを作成しました: {coll_name}/test_document")
            except Exception as coll_error:
                print(f"コレクション '{coll_name}' の作成中にエラー: {coll_error}")
    except Exception as e:
        print(f"テストドキュメント作成エラー: {e}")

    # 環境変数 WHISPER_JOBS_COLLECTION に該当するコレクションも確認
    target = os.environ.get("WHISPER_JOBS_COLLECTION")
    if target:
        try:
            print(f"Checking contents of collection `{target}`...")
            docs = list(db.collection(target).stream())
            print(f"Found {len(docs)} documents in collection `{target}`:")
            for doc in docs:
                print(f"- {doc.id}: {doc.to_dict()!r}")
        except Exception as e:
            print(f"Error accessing collection `{target}`: {e}")
#%%
if __name__ == "__main__":
    main()
#%%
load_environment()
# %%
# プロジェクトルートからのパスを組み立て
