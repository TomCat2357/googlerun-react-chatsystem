# backend/app/api/whisper_batch.py
import os
import time
import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from google.cloud import firestore, batch_v1
from google.cloud.firestore import Transaction
from google.cloud.batch_v1.types import (
    Job,
    TaskGroup,
    TaskSpec,
    Runnable,
    ComputeResource,
    AllocationPolicy,
    LogsPolicy,
    Environment,
)
from google.protobuf.duration_pb2 import Duration # Correct import for Duration

from common_utils.logger import logger # Use FastAPI logger
from common_utils.class_types import (
    WhisperFirestoreData,
    WhisperPubSubMessageData, # For handling notifications
    WhisperBatchParameter,    # For setting Batch job env vars
)

# Firestore client (initialized globally or passed around)
# Ensure GOOGLE_APPLICATION_CREDENTIALS is set in the FastAPI server's environment
db: firestore.Client = firestore.Client()

router = APIRouter()

# --- Configuration (should be loaded from .env by FastAPI's main.py) ---
# These will be fetched from os.environ, assuming they are set.
# GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"] # Already used in whisper.py
# GCP_REGION = os.environ["GCP_REGION"]
# BATCH_IMAGE_URL = os.environ["BATCH_IMAGE_URL"]
# HF_AUTH_TOKEN = os.environ["HF_AUTH_TOKEN"] # Also used by whisper_batch
# WHISPER_JOBS_COLLECTION = os.environ["WHISPER_JOBS_COLLECTION"]
# MAX_PROCESSING_JOBS = int(os.environ.get("MAX_PROCESSING_JOBS", "5")) # Default if not set
# EMAIL_NOTIFICATION_ENABLED = os.environ.get("EMAIL_NOTIFICATION", "false").lower() == "true"


def _get_env_var(var_name: str, default: Optional[str] = None) -> str:
    """Helper to get environment variables, raising an error if not found and no default."""
    value = os.environ.get(var_name, default)
    if value is None:
        logger.error(f"Environment variable {var_name} not set.")
        raise ValueError(f"Missing environment variable: {var_name}")
    return value

def _get_current_processing_job_count() -> int:
    """Counts currently 'processing' jobs in Firestore."""
    try:
        whisper_jobs_collection = _get_env_var("WHISPER_JOBS_COLLECTION")
        processing_count_snapshot = (
            db.collection(whisper_jobs_collection)
            .where("status", "==", "processing")
            .count()
            .get()
        )
        
        # Correctly extract count from AggregationQueryResult
        if processing_count_snapshot and processing_count_snapshot[0]:
            agg_result = processing_count_snapshot[0][0]
            if hasattr(agg_result, 'value'):
                return int(agg_result.value)
        return 0 # Default to 0 if parsing fails or no result
    except Exception as e:
        logger.error(f"Error counting processing jobs: {e}", exc_info=True)
        return 0 # Treat error as no jobs processing to be safe, or handle as critical

def _create_gcp_batch_job(job_data: WhisperFirestoreData) -> str:
    """
    Creates and launches a GCP Batch job for a given WhisperFirestoreData.
    This is adapted from whisper_queue/app/main.py's create_batch_job.
    """
    gcp_project_id = _get_env_var("GCP_PROJECT_ID")
    gcp_region = _get_env_var("GCP_REGION")
    batch_image_url = _get_env_var("BATCH_IMAGE_URL")
    hf_auth_token = _get_env_var("HF_AUTH_TOKEN")
    
    logger.info(f"Creating GCP Batch job for Firestore job_id: {job_data.job_id}, file_hash: {job_data.file_hash}")

    batch_client: batch_v1.BatchServiceClient = batch_v1.BatchServiceClient()
    batch_job_name: str = f"whisper-{job_data.job_id}-{int(time.time())}"

    job = Job()
    # job.name = batch_job_name # Name is set in CreateJobRequest.job_id

    task_spec = TaskSpec()
    container = Runnable.Container()
    container.image_uri = batch_image_url
    container.commands = ["python3", "/app/main.py"] # Command for whisper_batch/app/main.py

    # Prepare environment variables for the batch job container
    if not job_data.audio_file_path or not job_data.transcription_file_path:
        raise ValueError("audio_file_path or transcription_file_path is missing in job_data")

    batch_env_params = WhisperBatchParameter(
        JOB_ID=job_data.job_id,
        FULL_AUDIO_PATH=f"gs://{job_data.gcs_bucket_name}/{job_data.audio_file_path}",
        FULL_TRANSCRIPTION_PATH=f"gs://{job_data.gcs_bucket_name}/{job_data.transcription_file_path}",
        HF_AUTH_TOKEN=hf_auth_token,
        NUM_SPEAKERS=str(job_data.num_speakers) if job_data.num_speakers is not None else "",
        MIN_SPEAKERS=str(job_data.min_speakers),
        MAX_SPEAKERS=str(job_data.max_speakers),
        LANGUAGE=job_data.language,
        INITIAL_PROMPT=job_data.initial_prompt,
    )

    runnable_env = Environment()
    runnable_env.variables = {k: v for k, v in batch_env_params.model_dump().items() if v is not None}
    
    runnable = Runnable()
    runnable.container = container
    runnable.environment = runnable_env
    task_spec.runnables = [runnable]

    resources = ComputeResource()
    resources.cpu_milli = int(_get_env_var("BATCH_CPU_MILLI", "2000")) # e.g., 2000 for 2 vCPU
    resources.memory_mib = int(_get_env_var("BATCH_MEMORY_MIB", "16384")) # e.g., 16384 for 16GB
    task_spec.compute_resource = resources
    task_spec.max_retry_count = 2
    
    # Duration from audio_duration_ms
    audio_duration_seconds = job_data.audio_duration_ms / 1000
    # Ensure max_run_duration is at least a minimum value (e.g., 5 mins)
    # plus some buffer for the audio duration.
    # The logic from whisper_queue was max(300, audio_duration_seconds).
    # Let's use a base + audio duration * factor.
    base_duration_sec = 300 # 5 minutes
    # Timeout factor for audio, can be configured
    audio_timeout_multiplier = float(_get_env_var("AUDIO_TIMEOUT_MULTIPLIER", "2.0"))
    calculated_max_duration = base_duration_sec + (audio_duration_seconds * audio_timeout_multiplier)

    task_spec.max_run_duration = Duration(seconds=int(calculated_max_duration))


    task_group = TaskGroup()
    task_group.task_count = 1
    task_group.task_spec = task_spec
    job.task_groups = [task_group]

    allocation_policy_config = AllocationPolicy()
    location_policy = AllocationPolicy.LocationPolicy()
    location_policy.allowed_locations = [f"regions/{gcp_region}"]
    allocation_policy_config.location = location_policy

    instance_policy = AllocationPolicy.InstancePolicy()
    instance_policy.machine_type = _get_env_var("BATCH_MACHINE_TYPE", "n1-standard-4")
    
    # GPU Configuration
    use_gpu_str = _get_env_var("BATCH_USE_GPU", "true").lower()
    if use_gpu_str == "true":
        accelerator = AllocationPolicy.Accelerator()
        accelerator.type_ = _get_env_var("BATCH_GPU_TYPE", "nvidia-tesla-t4") # e.g., nvidia-tesla-t4
        accelerator.count = int(_get_env_var("BATCH_GPU_COUNT", "1"))
        instance_policy.accelerators = [accelerator]

    instance_policy_or_template = AllocationPolicy.InstancePolicyOrTemplate()
    instance_policy_or_template.policy = instance_policy
    if use_gpu_str == "true": # Only install drivers if GPU is used
        instance_policy_or_template.install_gpu_drivers = True # GCP Batch will install drivers
    
    allocation_policy_config.instances = [instance_policy_or_template]
    job.allocation_policy = allocation_policy_config

    job.logs_policy = LogsPolicy()
    job.logs_policy.destination = LogsPolicy.Destination.CLOUD_LOGGING

    create_request = batch_v1.CreateJobRequest(
        parent=f"projects/{gcp_project_id}/locations/{gcp_region}",
        job_id=batch_job_name,
        job=job,
    )
    
    created_job = batch_client.create_job(create_request)
    logger.info(f"GCP Batch job created: {created_job.name}, UID: {created_job.uid}, State: {created_job.status.state}")
    return created_job.name # Return the full job name

async def trigger_whisper_batch_processing(job_id: str, background_tasks: BackgroundTasks):
    """
    Fetches job data, checks capacity, updates status, and launches GCP Batch job.
    To be called by whisper.py after a new job is created.
    トランザクションを使用して同時実行の競合を防止します。
    """
    whisper_jobs_collection = _get_env_var("WHISPER_JOBS_COLLECTION")
    job_ref = db.collection(whisper_jobs_collection).document(job_id)
    max_processing_jobs = int(_get_env_var("MAX_PROCESSING_JOBS", "5"))

    @firestore.transactional
    def _reserve_slot(tx: Transaction) -> Optional[WhisperFirestoreData]:
        # ① 現在の処理中件数をカウント
        processing_count = (
            db.collection(whisper_jobs_collection)
            .where("status", "==", "processing")
            .count()
            .get(transaction=tx)[0][0]
            .value
        )

        if processing_count >= max_processing_jobs:
            return None  # キューのまま待機

        snap = job_ref.get(transaction=tx)
        if not snap.exists or snap.get("status") != "queued":
            return None  # 競合で別スレッドが処理した

        # ② status を processing へ更新
        tx.update(
            job_ref,
            {
                "status": "processing",
                "process_started_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        data = snap.to_dict() | {"job_id": job_id, "status": "processing"}
        return WhisperFirestoreData(**data)

    try:
        reserved_job = _reserve_slot(db.transaction())
        if not reserved_job:
            logger.info(f"Job {job_id} はまだ待機中（同時実行上限に達したか競合）。")
            return  # queued のまま戻る

        # ③ Batch ジョブ生成は別スレッドで
        background_tasks.add_task(_execute_batch_job_creation, reserved_job, job_ref)
        logger.info(f"Scheduled GCP Batch job creation for {job_id} in background.")

    except Exception as e:
        logger.error(f"Failed to update job {job_id} status or schedule batch creation: {e}", exc_info=True)
        # 失敗した場合はステータスを失敗に更新
        job_ref.update({
            "status": "failed",
            "error_message": f"Failed during pre-batch setup: {str(e)}",
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        raise HTTPException(status_code=500, detail=f"Error preparing job {job_id} for batch.")

def _execute_batch_job_creation(job_data: WhisperFirestoreData, job_ref: firestore.DocumentReference):
    """Helper function to be run in a background task for creating the GCP Batch job."""
    try:
        gcp_batch_job_name = _create_gcp_batch_job(job_data)
        job_ref.update({
            "gcp_batch_job_name": gcp_batch_job_name,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Successfully launched GCP Batch job {gcp_batch_job_name} for Whisper job {job_data.job_id}")
    except Exception as e:
        logger.error(f"Failed to create GCP Batch job for Whisper job {job_data.job_id} in background: {e}", exc_info=True)
        job_ref.update({
            "status": "failed",
            "error_message": f"Failed to launch GCP Batch job: {str(e)}",
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        })

def _send_email_notification_internal(user_email: Optional[str], job_id: str, status: str, error_message: Optional[str] = None):
    """Internal logic for sending email notifications."""
    email_notification_enabled_str = _get_env_var("EMAIL_NOTIFICATION", "false").lower()
    if not email_notification_enabled_str == "true" or not user_email:
        logger.debug(f"Email notification skipped for job {job_id}. Enabled: {email_notification_enabled_str}, Email: {'Provided' if user_email else 'Not Provided'}")
        return

    try:
        # This is a placeholder. Implement actual email sending logic here.
        # Example: Using a third-party service or GCP SMTP relay.
        subject = f"Whisper Job {job_id} - Status: {status.capitalize()}"
        body = f"Your Whisper transcription job (ID: {job_id}) has {status}.\n"
        if status == "failed" and error_message:
            body += f"Error details: {error_message}\n"
        body += "\nPlease check the application for more details."
        
        logger.info(f"Simulating email notification to {user_email} for job {job_id}, status: {status}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body: {body}")
        # 実際のメール発送ロジック追加 (e.g. SendGrid, AWS SES, etc.)
    except Exception as e:
        logger.error(f"Error sending email notification for job {job_id}: {e}", exc_info=True)


def handle_batch_job_notification(notification_data: WhisperPubSubMessageData):
    """
    Processes notifications about GCP Batch job completion or failure.
    This function would be called by an API endpoint that receives Pub/Sub messages
    forwarded from GCP Batch job state changes.
    """
    job_id = notification_data.job_id
    event_type = notification_data.event_type
    error_msg = notification_data.error_message
    
    whisper_jobs_collection = _get_env_var("WHISPER_JOBS_COLLECTION")
    job_ref = db.collection(whisper_jobs_collection).document(job_id)
    
    logger.info(f"Handling batch job notification: job_id={job_id}, event_type={event_type}, error='{error_msg}'")

    try:
        job_doc = job_ref.get()
        if not job_doc.exists:
            logger.error(f"Job {job_id} not found in Firestore while handling notification.")
            return

        job_data_dict = job_doc.to_dict()
        job_data_dict["job_id"] = job_id # Ensure job_id is part of the dict for Pydantic model
        current_job_data = WhisperFirestoreData(**job_data_dict)


        if event_type in ("job_completed", "batch_complete"):
            # Check if already completed to avoid reprocessing notifications
            if current_job_data.status == "completed":
                logger.info(f"Job {job_id} already marked as completed. Ignoring notification.")
                return

            update_payload = {
                "status": "completed",
                "process_ended_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "error_message": None # Clear any previous error
            }
            job_ref.update(update_payload)
            logger.info(f"Job {job_id} successfully marked as completed.")
            _send_email_notification_internal(current_job_data.user_email, job_id, "completed")

        elif event_type in ("job_failed", "batch_failed"):
             # Check if already failed to avoid reprocessing notifications
            if current_job_data.status == "failed" and current_job_data.error_message == error_msg:
                logger.info(f"Job {job_id} already marked as failed with the same error. Ignoring notification.")
                return

            update_payload = {
                "status": "failed",
                "error_message": error_msg or "Batch job failed without specific error message.",
                "process_ended_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
            job_ref.update(update_payload)
            logger.error(f"Job {job_id} marked as failed. Error: {error_msg}")
            _send_email_notification_internal(current_job_data.user_email, job_id, "failed", error_msg)
        
        elif event_type in ("job_canceled"): # Assuming cancel comes from API, not batch
             logger.info(f"Job {job_id} cancellation notification received (usually handled by API). Status: {current_job_data.status}")
             # Typically, the API endpoint for cancel would have already updated Firestore.
             # This handler might not need to do much for 'job_canceled' from batch notifications,
             # unless batch itself can be cancelled and emit such an event.

        else:
            logger.warning(f"Received unhandled event type '{event_type}' for job {job_id}.")

    except Exception as e:
        logger.error(f"Error processing batch job notification for job {job_id}: {e}", exc_info=True)
        # Potentially update Firestore to an error state if the job is stuck,
        # but be careful not to overwrite a definitive "completed" or "failed" state from Batch.

# Example API endpoint for receiving notifications (e.g., from a Cloud Function)
# This is where Pub/Sub messages from GCP Batch (after being processed by a Cloud Function) would be sent.
@router.post("/notify_batch_completion", include_in_schema=True, summary="Handles GCP Batch Job Notifications")
async def notify_batch_completion_endpoint(request: Request, notification: WhisperPubSubMessageData):
    # Simple auth: check for a specific header or originating IP if needed, or use GCP IAM for service-to-service.
    # For now, assuming the caller (e.g., Cloud Function) is trusted.
    logger.info(f"Received batch completion notification via API for job ID: {notification.job_id}")
    try:
        # It's better to run this in a background task if it involves significant work
        # or further I/O, to quickly return a response to the caller.
        # However, Firestore updates are relatively quick.
        handle_batch_job_notification(notification)
        return {"status": "success", "message": "Notification processed."}
    except Exception as e:
        logger.error(f"API Error processing batch notification for job {notification.job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing notification.")