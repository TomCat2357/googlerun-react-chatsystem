#!/usr/bin/env python
import base64
import json
import logging
import os
import time
from datetime import datetime, timedelta
from google.cloud import firestore, storage, batch_v1
from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
from google.cloud.batch_v1.types import Job, TaskSpec, ComputeResource, AllocationPolicy, LogsPolicy
from google.protobuf.duration_pb2 import Duration
from concurrent.futures import TimeoutError
import flask
import functions_framework

# 環境変数
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-project-id")
LOCATION = os.environ.get("GCP_REGION", "us-central1")
PUBSUB_TOPIC = os.environ.get("PUBSUB_TOPIC", "")
PUBSUB_SUBSCRIPTION = os.environ.get("PUBSUB_SUBSCRIPTION", "")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")
BATCH_IMAGE_URL = os.environ.get("BATCH_IMAGE_URL", "")
HF_AUTH_TOKEN = os.environ.get("HF_AUTH_TOKEN", "")
EMAIL_NOTIFICATION = os.environ.get("EMAIL_NOTIFICATION", "false").lower() == "true"

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Firestoreクライアント
db = firestore.Client()

# ストレージクライアント
storage_client = storage.Client()

def create_batch_job(job_id, user_id, user_email, gcs_audio_path):
    """Batchジョブを作成して起動する"""
    logger.info(f"バッチジョブの作成: {job_id}")
    
    # Batch APIクライアント初期化
    batch_client = batch_v1.BatchServiceClient()
    
    # バッチジョブ名（一意）
    batch_job_name = f"whisper-{job_id}-{int(time.time())}"
    
    # ジョブ定義の作成
    job = Job()
    job.name = batch_job_name
    
    # タスクスペック設定
    task_spec = TaskSpec()
    
    # コンテナ設定
    container = TaskSpec.Runnable.Container()
    container.image_uri = BATCH_IMAGE_URL
    
    # 環境変数設定
    container.environment = {
        "JOB_ID": job_id,
        "USER_ID": user_id,
        "USER_EMAIL": user_email,
        "GCS_AUDIO_PATH": gcs_audio_path,
        "HF_AUTH_TOKEN": HF_AUTH_TOKEN
    }
    
    # コマンド設定
    container.commands = ["python3", "/app/main.py"]
    
    run_as_runnable = TaskSpec.Runnable()
    run_as_runnable.container = container
    task_spec.runnables = [run_as_runnable]
    
    # リソース設定
    resources = ComputeResource()
    resources.cpu_milli = 2000  # 2 CPU コア
    resources.memory_mib = 16384  # 16 GB メモリ
    
    # GPUを追加
    resources.accelerators = [
        batch_v1.types.AcceleratorConfiguration(
            count=1,
            type_="nvidia-tesla-t4"
        )
    ]
    
    task_spec.compute_resource = resources
    task_spec.max_retry_count = 2
    task_spec.max_run_duration = Duration()
    task_spec.max_run_duration.seconds = 3600  # 1時間の実行制限
    
    # タスクグループの設定
    task_group = batch_v1.types.TaskGroup()
    task_group.task_count = 1
    task_group.task_spec = task_spec
    
    # ジョブにタスクグループを設定
    job.task_groups = [task_group]
    job.allocation_policy = AllocationPolicy()
    
    # ロケーション設定
    location_policy = AllocationPolicy.LocationPolicy()
    location_policy.allowed_locations = [f"regions/{LOCATION}"]
    job.allocation_policy.location = location_policy
    
    # ロギング設定
    job.logs_policy = LogsPolicy()
    job.logs_policy.destination = LogsPolicy.Destination.CLOUD_LOGGING
    
    # バッチジョブの作成リクエスト
    create_request = batch_v1.CreateJobRequest()
    create_request.job = job
    create_request.job_id = batch_job_name
    create_request.parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
    
    # ジョブを作成
    created_job = batch_client.create_job(create_request)
    
    # FirestoreとGCSのメタデータを更新
    update_job_metadata(job_id, user_id, {
        "batch_job_name": batch_job_name,
        "status": "processing",
        "progress": 10,
        "updated_at": firestore.SERVER_TIMESTAMP
    })
    
    logger.info(f"バッチジョブが作成されました: {batch_job_name}")
    return batch_job_name

def update_job_metadata(job_id, user_id, updates):
    """FirestoreとGCSのジョブメタデータを更新"""
    try:
        # Firestoreを更新
        job_ref = db.collection("whisper_jobs").document(job_id)
        job_ref.update(updates)
        
        # GCSメタデータも更新
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        metadata_path = f"whisper/{user_id}/{job_id}/metadata.json"
        metadata_blob = bucket.blob(metadata_path)
        
        if metadata_blob.exists():
            job_data = json.loads(metadata_blob.download_as_string())
            job_data.update(updates)
            
            # ServerTimestampを処理
            if "updated_at" in updates and updates["updated_at"] == firestore.SERVER_TIMESTAMP:
                job_data["updated_at"] = int(time.time())
            
            metadata_blob.upload_from_string(
                json.dumps(job_data, ensure_ascii=False),
                content_type="application/json"
            )
    except Exception as e:
        logger.error(f"メタデータ更新エラー: {e}")

def send_email_notification(user_email, job_id, status):
    """処理完了/失敗のメール通知を送信"""
    if not EMAIL_NOTIFICATION or not user_email:
        return
    
    try:
        # ここで実際のメール送信処理を実装
        # Sendgrid、GCP SMTPリレー、その他のメールサービスを使用
        logger.info(f"メール通知送信: {user_email}, ジョブID: {job_id}, 状態: {status}")
    except Exception as e:
        logger.error(f"メール送信エラー: {e}")

def process_next_job():
    """キューから次のジョブを取得して処理する"""
    try:
        # 処理中のジョブをカウント
        processing_count = db.collection("whisper_jobs").where("status", "==", "processing").count().get()[0][0]
        
        # 処理中のジョブが多すぎる場合は待機
        if processing_count >= 5:  # 同時処理数の上限
            logger.info(f"処理中のジョブが多すぎます: {processing_count}件")
            return False
        
        # 最も古いqueuedジョブを取得
        queued_jobs = db.collection("whisper_jobs").where("status", "==", "queued").order_by("created_at").limit(1).stream()
        
        job = next(queued_jobs, None)
        if not job:
            logger.info("処理待ちのジョブがありません")
            return False
        
        # ジョブデータ取得
        job_data = job.to_dict()
        job_id = job.id
        user_id = job_data.get("user_id")
        user_email = job_data.get("user_email")
        gcs_audio_path = job_data.get("gcs_audio_path")
        
        # バッチジョブを作成して起動
        batch_job_name = create_batch_job(job_id, user_id, user_email, gcs_audio_path)
        
        logger.info(f"ジョブを処理中に変更: {job_id}, バッチジョブ: {batch_job_name}")
        return True
        
    except Exception as e:
        logger.error(f"次のジョブ処理エラー: {e}")
        return False

def handle_batch_completion(job_id, user_id, user_email, success, error_message=None):
    """バッチジョブの完了または失敗を処理"""
    try:
        status = "completed" if success else "failed"
        
        # ジョブステータスを更新
        updates = {
            "status": status,
            "progress": 100 if success else 0,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        
        if error_message:
            updates["error_message"] = error_message
            
        update_job_metadata(job_id, user_id, updates)
        
        # メール通知
        if EMAIL_NOTIFICATION and user_email:
            send_email_notification(user_email, job_id, status)
            
        logger.info(f"バッチ処理{status}: {job_id}")
        
        # 次のジョブの処理を試みる
        process_next_job()
        
    except Exception as e:
        logger.error(f"バッチ完了処理エラー: {e}")

def process_pubsub_message(message_data):
    """Pub/Subメッセージを処理する"""
    try:
        job_id = message_data.get("job_id")
        user_id = message_data.get("user_id")
        user_email = message_data.get("user_email")
        event_type = message_data.get("event_type", "")
        
        if not job_id or not user_id:
            logger.error("必須フィールドがありません: job_id、user_id")
            return
        
        logger.info(f"メッセージ処理: {event_type}, ジョブID: {job_id}")
        
        if event_type == "new_job" or event_type == "start_job":
            # 新規ジョブまたは開始リクエスト - 次のジョブ処理を試みる
            process_next_job()
            
        elif event_type == "batch_complete":
            # バッチ処理完了
            success = message_data.get("success", False)
            error_message = message_data.get("error_message")
            handle_batch_completion(job_id, user_id, user_email, success, error_message)
            
        elif event_type == "cancel_job":
            # キャンセル処理 - 特に何もしない（Firestoreはすでに更新済み）
            logger.info(f"ジョブキャンセル: {job_id}")
            
        else:
            logger.warning(f"不明なイベントタイプ: {event_type}")
            
    except Exception as e:
        logger.error(f"メッセージ処理エラー: {e}")

@functions_framework.http
def whisper_queue_http(request):
    """HTTP経由で特定の操作をトリガーするエンドポイント"""
    if request.method == "GET":
        # 手動でジョブ処理を進める場合
        result = process_next_job()
        return {"status": "success", "processed": result}
    
    elif request.method == "POST":
        # 特定のジョブの状態を更新する場合
        try:
            data = request.get_json()
            job_id = data.get("job_id")
            status = data.get("status")
            
            if not job_id or not status:
                return {"status": "error", "message": "job_idとstatusは必須です"}, 400
            
            job_ref = db.collection("whisper_jobs").document(job_id)
            job_data = job_ref.get().to_dict()
            
            if not job_data:
                return {"status": "error", "message": f"ジョブが見つかりません: {job_id}"}, 404
            
            user_id = job_data.get("user_id")
            
            # ステータス更新
            update_job_metadata(job_id, user_id, {
                "status": status,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
            return {"status": "success", "message": f"ジョブ {job_id} を {status} に更新しました"}
            
        except Exception as e:
            logger.error(f"HTTP処理エラー: {e}")
            return {"status": "error", "message": str(e)}, 500
    
    return {"status": "error", "message": "サポートされていないメソッド"}, 405

@functions_framework.cloud_event
def whisper_queue_pubsub(cloud_event):
    """Pub/Sub経由でメッセージを受信し処理するエントリーポイント"""
    try:
        # メッセージデータをデコード
        envelope = json.loads(cloud_event.data["message"]["data"])
        
        # JSON形式でない場合はBase64デコード
        if isinstance(envelope, str):
            envelope = json.loads(base64.b64decode(envelope).decode("utf-8"))
            
        logger.info(f"Pub/Subメッセージを受信: {envelope.get('event_type', 'unknown')}")
        
        # メッセージ処理
        process_pubsub_message(envelope)
        
        # 次のジョブ処理を実行
        process_next_job()
        
        return "OK"
    
    except Exception as e:
        logger.error(f"Pub/Sub処理エラー: {e}")
        return f"Error: {str(e)}", 500

def subscribe_to_pubsub():
    """Pub/Subサブスクリプションでメッセージを受信するループ処理"""
    subscriber = SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, PUBSUB_SUBSCRIPTION)
    
    def callback(message):
        try:
            logger.info(f"Message received: {message.message_id}")
            data = json.loads(message.data.decode("utf-8"))
            process_pubsub_message(data)
            message.ack()
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            message.nack()
    
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    logger.info(f"Listening for messages on {subscription_path}")
    
    try:
        # 指定した時間、メッセージを待機（実際の運用では無限ループにする）
        streaming_pull_future.result(timeout=3600)  # 1時間待機
    except TimeoutError:
        streaming_pull_future.cancel()
        logger.info("Subscription timeout, shutting down.")
    except Exception as e:
        logger.error(f"Subscription error: {e}")
        streaming_pull_future.cancel()

if __name__ == "__main__":
    # スタンドアロンモードで実行する場合
    logger.info("Whisper Queue Service starting...")
    
    # 起動時に既存のキューを処理
    process_next_job()
    
    # Pub/Subサブスクリプションを監視
    if PUBSUB_SUBSCRIPTION:
        subscribe_to_pubsub()
    else:
        logger.warning("PUBSUB_SUBSCRIPTION not set, running in HTTP-only mode")
        
        # 代わりに定期的にキューをポーリング
        while True:
            try:
                process_next_job()
                time.sleep(30)  # 30秒ごとにポーリング
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(60)  # エラー時は1分待機