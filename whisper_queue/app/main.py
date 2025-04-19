#!/usr/bin/env python
import base64
import json
import logging
import os
import time
import datetime
from google.cloud import firestore, storage, batch_v1
from google.cloud.pubsub_v1 import PublisherClient
from google.cloud.batch_v1.types import (
    Job,
    TaskSpec,
    ComputeResource,
    AllocationPolicy,
    LogsPolicy,
    Runnable,
    Environment,
    ComputeResource,
)
from google.protobuf.duration_pb2 import Duration
import functions_framework
from common_utils.class_types import (
    WhisperFirestoreData,
    WhisperPubSubMessageData,
    WhisperBatchParameter,
)

from dotenv import load_dotenv
from pathlib import Path

# スクリプトの場所を基準にする
BASE_DIR = Path(__file__).resolve().parent.parent
config_path = os.path.join(BASE_DIR, "config", ".env")
load_dotenv(config_path)

develop_config_path = os.path.join(BASE_DIR, "config_develop", ".env.develop")
if os.path.exists(develop_config_path):
    load_dotenv(develop_config_path)

# 環境変数
GCP_PROJECT_ID: str = os.environ.get("GCP_PROJECT_ID")
GCP_REGION: str = os.environ.get("GCP_REGION")
PUBSUB_TOPIC: str = os.environ.get("PUBSUB_TOPIC")
GCS_BUCKET_NAME: str = os.environ.get("GCS_BUCKET_NAME")
BATCH_IMAGE_URL: str = os.environ.get("BATCH_IMAGE_URL")
HF_AUTH_TOKEN: str = os.environ.get("HF_AUTH_TOKEN")
EMAIL_NOTIFICATION: bool = (
    os.environ.get("EMAIL_NOTIFICATION", "false").lower() == "true"
)
# コレクション名の環境変数を追加
WHISPER_JOBS_COLLECTION: str = os.environ.get("WHISPER_JOBS_COLLECTION")

# スクリプトの場所を基準にして、BASEDIRをつくって、GOOGLE_APPLICATION_CREDENTIALSについても絶対パスにする。
BASE_DIR = str(Path(__file__).resolve().parent.parent)
if BASE_DIR not in os.environ['GOOGLE_APPLICATION_CREDENTIALS']:
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(BASE_DIR, os.environ['GOOGLE_APPLICATION_CREDENTIALS'])

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Firestoreクライアント
#print('GOOGLE_APPLICATION_CREDENTIALS',os.environ['GOOGLE_APPLICATION_CREDENTIALS'])
db: firestore.Client = firestore.Client()

# ストレージクライアント
storage_client: storage.Client = storage.Client()


def create_batch_job(job_data: WhisperFirestoreData) -> str:
    """Batchジョブを作成して起動する"""
    """単体テストチェック済み_20250419 9:14"""
    logger.info(f"バッチジョブの作成: {job_data.job_id}, hash: {job_data.file_hash}")

    # Batch APIクライアント初期化
    batch_client: batch_v1.BatchServiceClient = batch_v1.BatchServiceClient()

    # バッチジョブ名（一意）
    batch_job_name: str = f"whisper-{job_data.job_id}-{int(time.time())}"

    # ジョブ定義の作成
    job: Job = Job()
    job.name = batch_job_name

    # タスクスペック設定
    task_spec: TaskSpec = TaskSpec()

    # コンテナ設定 - APIの構造変更に対応
    # 修正前: container: TaskSpec.Runnable.Container = TaskSpec.Runnable.Container()
    # 修正後: 現在のAPIに合わせた構造を使用
    container = Runnable.Container()  # または batch_v1.types.Runnable.Container()
    
    # 以下は元のままでOK
    container.image_uri = BATCH_IMAGE_URL

    # 環境変数設定
    batch_params: WhisperBatchParameter = WhisperBatchParameter(
        JOB_ID=job_data.job_id,
        AUDIO_PATH=f"{job_data.gcs_backet_name}/{job_data.audio_file_path}",
        TRANSCRIPTION_PATH=f"{job_data.gcs_backet_name}/{job_data.transcription_file_path}",
        HF_AUTH_TOKEN=HF_AUTH_TOKEN,
        PUBSUB_TOPIC=PUBSUB_TOPIC,
        GCP_PROJECT_ID=GCP_PROJECT_ID,
        GCP_REGION=GCP_REGION,
        NUM_SPEAKERS="" if not job_data.num_speakers else str(job_data.num_speakers),
        MIN_SPEAKERS=str(job_data.min_speakers),
        MAX_SPEAKERS=str(job_data.max_speakers),
        LANGUAGE=job_data.language,
        INITIAL_PROMPT=job_data.initial_prompt,
    )
    #container.environment = batch_params.model_dump()

    # コマンド設定
    container.commands = ["python3", "/app/main.py"]

    # ランナブル設定 - APIの構造変更に対応
    # 修正前: run_as_runnable: TaskSpec.Runnable = TaskSpec.Runnable()
    # 修正後:
    run_as_runnable = Runnable()  # または batch_v1.types.Runnable()
    run_as_runnable.container = container
    
    env = Environment()
    env_vars = {}
    for key, value in batch_params.model_dump().items():
        env_vars[key] = str(value)
    env.variables = env_vars
    run_as_runnable.environment = env
    
    task_spec.runnables = [run_as_runnable]

    # リソース設定 - CPUとメモリのみ
    resources: ComputeResource = ComputeResource()
    resources.cpu_milli = 2000  # 2 CPU コア
    resources.memory_mib = 16384  # 16 GB メモリ
    
    # ComputeResourceにはGPU設定はない
    task_spec.compute_resource = resources
    task_spec.max_retry_count = 2
    
    # Durationを正しく設定する - コンストラクタでsecondsパラメータを指定
    max_duration_seconds = max([300, job_data.audio_duration])
    task_spec.max_run_duration = Duration(seconds=max_duration_seconds)  # 最大実行時間は5分と音声ファイルの時間の大きい方

    # タスクグループの設定
    task_group: batch_v1.types.TaskGroup = batch_v1.types.TaskGroup()
    task_group.task_count = 1
    task_group.task_spec = task_spec

    # ジョブにタスクグループを設定
    job.task_groups = [task_group]
    
    # AllocationPolicyを作成してGPUを設定
    allocation_policy = AllocationPolicy()
    
    # ロケーション設定
    location_policy = AllocationPolicy.LocationPolicy()
    location_policy.allowed_locations = [f"regions/{GCP_REGION}"]
    allocation_policy.location = location_policy
    
    # インスタンスポリシーの設定
    instance_policy = AllocationPolicy.InstancePolicy()
    instance_policy.machine_type = "n1-standard-4"  # T4 GPUと互換性のあるマシンタイプ
    
    # GPU設定
    accelerator = AllocationPolicy.Accelerator()
    accelerator.type_ = "nvidia-tesla-t4"
    accelerator.count = 1
    instance_policy.accelerators = [accelerator]
    
    # インスタンスポリシーをAllocationPolicyに設定
    instance_policy_or_template = AllocationPolicy.InstancePolicyOrTemplate()
    instance_policy_or_template.policy = instance_policy
    instance_policy_or_template.install_gpu_drivers = True
    allocation_policy.instances = [instance_policy_or_template]
    
    # ジョブにAllocationPolicyを設定
    job.allocation_policy = allocation_policy

    # ロギング設定
    job.logs_policy = LogsPolicy()
    job.logs_policy.destination = LogsPolicy.Destination.CLOUD_LOGGING

    # バッチジョブの作成リクエスト
    create_request: batch_v1.CreateJobRequest = batch_v1.CreateJobRequest()
    create_request.job = job
    create_request.job_id = batch_job_name
    create_request.parent = f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}"

    # ジョブを作成
    created_job = batch_client.create_job(create_request)

    # created_jobの情報をログに表示
    logger.info(f"バッチジョブの詳細: {created_job.name}")
    logger.info(f"ジョブステータス: {created_job.status.state}")
    logger.info(f"ジョブUUID: {created_job.uid}")

    logger.info(f"バッチジョブが作成されました: {batch_job_name}")
    return batch_job_name


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
    """キューから次の複数ジョブを取得して処理する（トランザクション対応）"""
    try:
        # トランザクションを開始
        @firestore.transactional
        def select_jobs_transaction(transaction):
            # 処理中のジョブをカウント
            processing_count_snapshot = (
                db.collection(WHISPER_JOBS_COLLECTION)
                .where("status", "==", "processing")
                .count()
                .get(transaction=transaction)
            )
            processing_count = processing_count_snapshot[0][0]

            # 同時処理可能数を計算
            max_processing = int(os.getenv("MAX_PROCESSING_JOBS", 1))
            available_slots = max(0, max_processing - processing_count)

            if available_slots <= 0:
                logger.info(
                    "同時処理数の上限(%s)に達しているため、新規処理追加をスキップします (現在の処理数: %s)",
                    max_processing,
                    processing_count,
                )
                return []

            # 処理可能数だけキューからジョブを取得
            queued_jobs_query = (
                db.collection(WHISPER_JOBS_COLLECTION)
                .where("status", "==", "queued")
                .order_by("created_at")
                .limit(available_slots)
            )

            queued_jobs = list(queued_jobs_query.stream(transaction=transaction))

            if not queued_jobs:
                logger.info("処理待ちのジョブがありません")
                return []

            # 取得したジョブのリストと参照を保持
            jobs_to_process = []

            # 各ジョブのステータスを処理中に更新
            for job_doc in queued_jobs:
                job_data = WhisperFirestoreData(**job_doc.to_dict())
                job_ref = db.collection(WHISPER_JOBS_COLLECTION).document(
                    job_data.job_id
                )

                # ジョブのステータスを処理中に更新（トランザクション内で確実に実行）
                transaction.update(
                    job_ref,
                    {
                        "status": "processing",
                        "process_started_at": firestore.SERVER_TIMESTAMP,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                )

                jobs_to_process.append(job_data)

            return jobs_to_process

        # トランザクションを実行してジョブを「予約」する
        jobs_to_process = select_jobs_transaction(db.transaction())

        # トランザクション成功後、予約したジョブに対してバッチ処理を実行
        for job_data in jobs_to_process:
            try:
                # バッチジョブを作成して起動
                batch_job_name = create_batch_job(job_data)

                logger.info(
                    f"ジョブを処理開始: {job_data.job_id}, hash: {job_data.file_hash}, バッチジョブ: {batch_job_name}"
                )


            except Exception as e:
                # バッチジョブ作成時にエラーが発生した場合
                error_message = f"バッチジョブ作成エラー: {str(e)}"
                logger.error(error_message)

                # ジョブステータスをfailedに更新（トランザクション外で処理）
                job_ref = db.collection(WHISPER_JOBS_COLLECTION).document(
                    job_data.job_id
                )
                job_ref.update(
                    {
                        "status": "failed",
                        "error_message": error_message,
                        "process_ended_at": firestore.SERVER_TIMESTAMP,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    }
                )

    except Exception as e:
        logger.error(f"ジョブ処理エラー: {e}")


def handle_batch_completion(whisperPubSubMessageData: WhisperPubSubMessageData):
    """バッチジョブの完了を処理"""

    job_id = whisperPubSubMessageData.job_id

    try:
        # Firestoreからジョブデータを取得
        job_ref = db.collection(WHISPER_JOBS_COLLECTION).document(job_id)
        job_doc = job_ref.get()

        if not job_doc.exists:
            logger.error(f"ジョブが見つかりません: {job_id}")
            return

        job_data = WhisperFirestoreData(**job_doc.to_dict())

        # イベントタイプによる処理分岐 - 複数のイベントタイプをサポート
        if whisperPubSubMessageData.event_type in ("job_completed", "batch_complete"):
            # ジョブが正常に完了した場合
            logger.info(f"ジョブ正常完了: {job_id}")

            # ジョブ状態を完了に更新
            update_data = {
                "status": "completed",
                "process_ended_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
            job_ref.update(update_data)

            # メール通知（設定されている場合）
            if job_data.user_email:
                send_email_notification(job_data.user_email, job_id, "completed")

        elif whisperPubSubMessageData.event_type in ("job_failed", "batch_failed"):
            # ジョブが失敗した場合
            logger.error(
                f"ジョブ失敗: {job_id}, エラー: {whisperPubSubMessageData.error_message}"
            )

            # ジョブ状態を失敗に更新
            update_data = {
                "status": "failed",
                "error_message": whisperPubSubMessageData.error_message,
                "process_ended_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }

            job_ref.update(update_data)
    except Exception as e:
        logger.error(f"バッチ完了処理エラー: {e}")


def process_subscription_message(
    whisperPubSubMessageData: WhisperPubSubMessageData,
) -> None:
    """Pub/Subメッセージをsubscriotionして処理する"""
    try:

        # オブジェクトのプロパティを使用
        if not whisperPubSubMessageData.job_id:
            logger.error("必須フィールドがありません: job_id")
            return

        logger.debug(
            f"メッセージ処理: {whisperPubSubMessageData.event_type}, ジョブID: {whisperPubSubMessageData.job_id}, timestamp: {whisperPubSubMessageData.timestamp}"
        )

        # イベントタイプに基づいた処理
        if whisperPubSubMessageData.event_type == "new_job":
            logger.info(f"新規ジョブ受信: {whisperPubSubMessageData.job_id}")

        # バッチ処理完了イベント (本番とテスト両方のイベントタイプをサポート)
        elif whisperPubSubMessageData.event_type in ("batch_complete", "batch_failed", "job_completed", "job_failed"):
            # バッチ処理完了
            handle_batch_completion(whisperPubSubMessageData)

        elif whisperPubSubMessageData.event_type in ("cancel_job", "job_canceled"):
            # キャンセル処理 - 特に何もしない（Firestoreはすでに更新済み）
            logger.info(f"ジョブキャンセル: {whisperPubSubMessageData.job_id}")

        else:
            logger.warning(
                f"不明なイベントタイプ: {whisperPubSubMessageData.event_type}"
            )

    except Exception as e:
        logger.error(f"メッセージ処理エラー: {e}")


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

        # WhisperPubSubMessageDataオブジェクトに変換
        pubsub_message_data = WhisperPubSubMessageData(
            event_type=envelope.get("event_type"),
            job_id=envelope.get("job_id"),
            timestamp=envelope.get("timestamp"),
            error_message=envelope.get("error_message"),
        )
        for key in pubsub_message_data.model_dump().keys():
            if pubsub_message_data[key] is None and key != "error_message":
                raise ValueError(f"必須フィールドがありません: {key}")

        # メッセージ処理
        process_subscription_message(pubsub_message_data)

        # 次のジョブ処理を実行
        process_next_job()

        return "OK"

    except Exception as e:
        logger.error(f"Pub/Sub処理エラー: {e}")
        return f"Error: {str(e)}", 500
