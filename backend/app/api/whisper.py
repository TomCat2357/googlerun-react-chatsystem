# API ルート: whisper.py - Whisper音声文字起こし関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Body
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import os, json, io, base64, hashlib, math, datetime, uuid
import subprocess, shlex, tempfile
from pydantic import BaseModel
from pydub import AudioSegment
from google.cloud import storage, pubsub_v1, firestore
from google.cloud.firestore_v1 import FieldFilter, WriteBatch, Query
from google.cloud.firestore_v1._helpers import Timestamp
from functools import partial

from app.api.auth import get_current_user
from common_utils.logger import logger, create_dict_logger, log_request
from common_utils.class_types import WhisperUploadRequest, WhisperFirestoreData, WhisperPubSubMessageData, WhisperSegment, WhisperEditRequest

# Import the new batch processing trigger function and audio utils
from app.api.whisper_batch import trigger_whisper_batch_processing, _get_current_processing_job_count, _get_env_var # 必要な関数をインポート
from app.core.audio_utils import probe_duration, convert_audio_to_wav_16k_mono
from app.services.whisper_queue import enqueue_job_atomic, decrement_processing_counter

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 設定値の読み込み
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCS_BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
GCS_BUCKET = os.environ["GCS_BUCKET"]  # バケット名
PUBSUB_TOPIC = os.environ["PUBSUB_TOPIC"]
WHISPER_JOBS_COLLECTION = os.environ["WHISPER_JOBS_COLLECTION"]
GENERAL_LOG_MAX_LENGTH = int(os.environ["GENERAL_LOG_MAX_LENGTH"])
SENSITIVE_KEYS = os.environ["SENSITIVE_KEYS"].split(",")
# Whisper制限設定
WHISPER_MAX_SECONDS = int(os.environ["WHISPER_MAX_SECONDS"])
WHISPER_MAX_BYTES = int(os.environ["WHISPER_MAX_BYTES"])
# 最大音声サイズ設定（互換性のために残す）
MAX_AUDIO_BYTES = min(WHISPER_MAX_BYTES, int(os.environ.get("MAX_AUDIO_BYTES", 100 * 1024 * 1024)))  # WHISPER_MAX_BYTESとの小さい方
MAX_AUDIO_BASE64_CHARS = int(os.environ.get("MAX_AUDIO_BASE64_CHARS", int(WHISPER_MAX_BYTES * 1.5)))  # Base64エンコードによるオーバーヘッド考慮
# PROCESS_TIMEOUT_SECONDS と AUDIO_TIMEOUT_MULTIPLIER を .env から読み込む
PROCESS_TIMEOUT_SECONDS = int(os.environ.get("PROCESS_TIMEOUT_SECONDS", "300"))
AUDIO_TIMEOUT_MULTIPLIER = float(os.environ.get("AUDIO_TIMEOUT_MULTIPLIER", "2.0"))
FIRESTORE_MAX_DAYS = int(os.environ.get("FIRESTORE_MAX_DAYS", "30")) # 追加：デフォルト30日

router = APIRouter()

# 署名付きURL用のレスポンスモデル
class UploadUrlResponse(BaseModel):
    upload_url: str
    object_name: str

# 有効なステータス一覧 (WhisperFirestoreDataから取得)
VALID_STATUSES = set(WhisperFirestoreData._VALID_STATUSES)

# 辞書ロガーのセットアップ
create_dict_logger = partial(create_dict_logger, sensitive_keys=SENSITIVE_KEYS)

@router.post("/whisper/upload_url", response_model=UploadUrlResponse)
async def create_upload_url(
    content_type: str = Body(..., embed=True),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    音声ファイルをGCSに直接アップロードするための署名付きURLを生成
    """
    # 認証情報の確認
    user_id = current_user["uid"]
    
    # 一意のオブジェクト名の生成
    random_uuid = uuid.uuid4()
    blob_name = f"whisper/{user_id}/{random_uuid}"
    
    # 署名付きURLの生成
    bucket = storage.Client().bucket(GCS_BUCKET)
    blob = bucket.blob(blob_name)
    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="PUT",
        content_type=content_type,
    )
    
    logger.info(f"Generated upload URL for user {user_id}, object: {blob_name}")
    return {"upload_url": signed_url, "object_name": blob_name}

@router.post("/whisper")
async def upload_audio(
    request: Request, 
    whisper_request: WhisperUploadRequest,
    background_tasks: BackgroundTasks, # Add BackgroundTasks dependency
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        request_info: Dict[str, Any] = await log_request(
        request, current_user, GENERAL_LOG_MAX_LENGTH
        )

        # 認証情報の取得
        user_id: str = current_user["uid"]
        user_email: str = current_user.get("email", "")
        
        # middle_wareでフィルタリングされているので無いとは思うが念のためrequest_infoにX-Request-Idが設定されていることを確認する
        if "X-Request-Id" not in request_info:
            return JSONResponse(status_code=500, content={"detail": "X-Request-Idがリクエスト情報に含まれていません"})

        # GCSオブジェクト名が必要
        if not whisper_request.gcs_object:
            return JSONResponse(status_code=400, content={"detail": "GCSオブジェクト名が提供されていません"})
            
        # GCSから音声データを取得して検証
        storage_client_instance: storage.Client = storage.Client()
        bucket = storage_client_instance.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(whisper_request.gcs_object)
        
        # オブジェクトの存在確認
        if not blob.exists():
            return JSONResponse(status_code=404, content={"detail": "指定されたGCSオブジェクトが見つかりません"})
        
        # MIMEタイプとファイルサイズを取得
        blob.reload()  # メタデータを確実に取得
        mime_type = blob.content_type
        if not mime_type or not mime_type.startswith("audio/"):
            return JSONResponse(status_code=400, content={"detail": f"無効な音声フォーマット: {mime_type}"})
            
        # ファイルサイズのチェック
        audio_size = blob.size
        if audio_size > WHISPER_MAX_BYTES:
            return JSONResponse(status_code=413, content={"detail": f"音声ファイルが大きすぎます（最大{WHISPER_MAX_BYTES/1024/1024:.1f}MB）"})
            
        # 音声データをメモリに読み込まずにハッシュを計算（ランダムなUUIDを代わりに使用）
        file_hash = hashlib.sha256(f"{whisper_request.gcs_object}-{datetime.datetime.now().isoformat()}".encode()).hexdigest()
        
        # MIMEタイプから拡張子を取得
        mime_mapping: Dict[str, str] = {
            "audio/wav": ".wav",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/webm": ".webm",
            "audio/aac": ".aac",
            "audio/m4a": ".m4a",
            "audio/x-m4a": ".m4a",
        }
        audio_file_extension: Optional[str] = mime_mapping.get(mime_type)
        if not audio_file_extension:
            return JSONResponse(status_code=400, content={"detail": f"サポートされていない音声フォーマット: {mime_type}"})
        
        audio_duration_ms = 0
        converted_wav_path = ""
        final_audio_size = audio_size
        original_filename_for_probe = whisper_request.original_name or f"audio{audio_file_extension or '.tmp'}"

        try:
            # 一時ファイルにダウンロード
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(original_filename_for_probe)[1]) as tmp_original_audio_file:
                blob.download_to_filename(tmp_original_audio_file.name)
                tmp_original_audio_file.flush()
                original_local_path = tmp_original_audio_file.name

                # ffprobeで元の音声の長さを取得
                seconds = probe_duration(original_local_path)
                audio_duration_ms = int(seconds * 1000)
                logger.debug(f"元の音声長さ: {audio_duration_ms} ms")

                # 音声の長さチェック（秒単位に変換）
                if audio_duration_ms > WHISPER_MAX_SECONDS * 1000:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"音声の長さが制限を超えています（最大{WHISPER_MAX_SECONDS/60:.1f}分）"}
                    )
                
                # 固定ビットレートのWAVに変換
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_converted_audio_file:
                    converted_wav_path = tmp_converted_audio_file.name

                convert_audio_to_wav_16k_mono(original_local_path, converted_wav_path)
                logger.info(f"音声を16kHzモノラルWAVに変換しました: {converted_wav_path}")
                final_audio_size = os.path.getsize(converted_wav_path)
                audio_file_extension = ".wav" # 拡張子を.wavに固定
        except Exception as e:
            logger.error("音声長さの取得に失敗しました: %s", str(e))
            return JSONResponse(status_code=400, content={"detail": f"音声長さの取得に失敗しました: {str(e)}"})
        
        # ENV テンプレートから直接フルパスを組み立て
        audio_blob_filename = os.environ["WHISPER_AUDIO_BLOB"].format(
            file_hash=file_hash,
            ext="wav" # 拡張子をwavに固定
        )
        audio_gcs_full_path = f"gs://{GCS_BUCKET_NAME}/{audio_blob_filename}"
        
        # 結合トランスクリプト出力用のパス
        combine_blob_filename = os.environ["WHISPER_COMBINE_BLOB"].format(file_hash=file_hash)
        # combine_uri = f"gs://{GCS_BUCKET_NAME}/{combine_blob_filename}" # この変数は直接使わない

        # 変換されたWAVファイルをGCSの最終的な場所にアップロード
        destination_bucket = storage_client_instance.bucket(GCS_BUCKET_NAME)
        destination_blob = destination_bucket.blob(audio_blob_filename)
        destination_blob.upload_from_filename(converted_wav_path)
        logger.info(f"変換された音声をアップロードしました: {audio_gcs_full_path}")

        # 元のアップロード用の一時GCSオブジェクトを削除
        temp_gcs_blob = storage_client_instance.bucket(GCS_BUCKET_NAME).blob(whisper_request.gcs_object)
        if temp_gcs_blob.exists():
            temp_gcs_blob.delete()
            logger.info(f"一時GCSオブジェクトを削除しました: gs://{GCS_BUCKET_NAME}/{whisper_request.gcs_object}")
            
        # ローカル一時ファイルを削除
        if os.path.exists(original_local_path):
            os.remove(original_local_path)
        if os.path.exists(converted_wav_path):
            os.remove(converted_wav_path)

        # Firestoreにジョブ情報を記録（トランザクション利用）
        job_id: str = str(uuid.uuid4()) # server-generated unique ID
        timestamp = firestore.SERVER_TIMESTAMP

        whisper_job_data = WhisperFirestoreData(
            job_id=job_id,
            user_id=user_id,
            user_email=current_user.get("email", ""), 
            filename=whisper_request.original_name or os.path.basename(whisper_request.gcs_object),
            description=whisper_request.description,
            recording_date=whisper_request.recording_date,
            gcs_bucket_name=GCS_BUCKET_NAME,
            audio_duration_ms=audio_duration_ms, 
            audio_size=final_audio_size, # 変換後のファイルサイズを使用
            file_hash=file_hash,
            language=whisper_request.language,
            initial_prompt=whisper_request.initial_prompt,
            status="queued", # Initial status
            created_at=timestamp,
            updated_at=timestamp,
            tags=whisper_request.tags or [],
            num_speakers=whisper_request.num_speakers,
            min_speakers=whisper_request.min_speakers or 1, 
            max_speakers=whisper_request.max_speakers or 1
        )

        # トランザクションを使ってジョブを登録
        job_dict = whisper_job_data.model_dump()
        job_dict["id"] = job_id  # キーに追加
        enqueue_job_atomic(job_dict)
        logger.info(f"Whisper job {job_id} queued in Firestore with atomic transaction.")

        # Trigger batch processing (asynchronously)
        # This will check processing limits and then launch the GCP Batch Job
        # The trigger_whisper_batch_processing itself might use background_tasks
        # if the GCP Batch job creation is slow.
        # Pass the job_id, the function will fetch the full data from Firestore.
        background_tasks.add_task(trigger_whisper_batch_processing, job_id, background_tasks)
        logger.info(f"Scheduled batch processing trigger for job {job_id}.")
        
        # Pub/Sub notification for "new_job" is no longer needed here if batch is triggered directly.
        # If other systems rely on this Pub/Sub message, it can be kept.
        # For now, let's assume direct triggering replaces the need for this specific Pub/Sub message.
        # publisher: pubsub_v1.PublisherClient = pubsub_v1.PublisherClient()
        # topic_path: str = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC)
        # current_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # message_data_obj = WhisperPubSubMessageData( # Ensure class name matches
        #     job_id=job_id,
        #     event_type="new_job", # This event might still be useful for other listeners
        #     timestamp=current_time_iso
        # )
        # message_bytes: bytes = message_data_obj.model_dump_json().encode("utf-8") # Use model_dump_json for Pydantic v2+
        # publish_future: pubsub_v1.publisher.futures.Future = publisher.publish(topic_path, data=message_bytes)
        # publish_future.result() # Wait for publish to complete
        # logger.debug(f"Published 'new_job' event to Pub/Sub for job {job_id}")
        
        response_data = {"status": "success", "job_id": job_id, "file_hash": file_hash, "message": "Job queued for processing."}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )

    except HTTPException as he:
        logger.error(f"HTTP Exception in audio upload: {he.detail}", exc_info=True)
        raise he
    except Exception as e:
        logger.exception("General error during audio upload and batch trigger.") # Default logger.exception logs stack trace
        # Consider specific error handling for batch trigger failures if not an HTTPException
        raise HTTPException(status_code=500, detail=f"Upload or batch trigger error: {str(e)}")

async def check_and_update_timeout_jobs(db: firestore.Client, user_id_for_filter: Optional[str] = None):
    """
    処理中のジョブでタイムアウトしたものを検索し、ステータスを 'failed' に更新する。
    user_id_for_filter が指定された場合、そのユーザーのジョブのみを対象とする。
    指定されない場合は、全ユーザーの 'processing' ジョブを対象とする。
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    processing_jobs_query = db.collection(WHISPER_JOBS_COLLECTION).where(
        filter=FieldFilter("status", "in", ["processing", "launched"])
    )
    # 特定ユーザーのジョブのみを対象とする場合
    # if user_id_for_filter:
    #     processing_jobs_query = processing_jobs_query.where(filter=FieldFilter("user_id", "==", user_id_for_filter))

    timed_out_jobs_batch = db.batch()
    updates_count = 0

    for job_snap in processing_jobs_query.stream():
        job_data_dict = job_snap.to_dict()
        if not job_data_dict:
            continue

        # job_id をドキュメントIDから取得
        job_data_dict["job_id"] = job_snap.id
        
        try:
            # WhisperFirestoreDataでパースして型安全にアクセス
            job_data = WhisperFirestoreData(**job_data_dict)

            process_started_at = job_data.process_started_at
            if not process_started_at:
                logger.warning(f"Job {job_data.job_id} is '{job_data.status}' but 'process_started_at' is not set. Skipping timeout check.")
                continue

            # FirestoreのTimestamp型をdatetimeに変換
            if isinstance(process_started_at, Timestamp):
                process_started_at_dt = process_started_at.to_datetime().replace(tzinfo=datetime.timezone.utc)
            elif isinstance(process_started_at, datetime.datetime):
                if process_started_at.tzinfo is None:
                    process_started_at_dt = process_started_at.replace(tzinfo=datetime.timezone.utc)
                else:
                    process_started_at_dt = process_started_at.astimezone(datetime.timezone.utc)
            else:
                logger.warning(f"Job {job_data.job_id} has invalid 'process_started_at' type: {type(process_started_at)}. Skipping.")
                continue

            audio_duration_ms = job_data.audio_duration_ms or 0
            
            # タイムアウト秒数の計算
            timeout_seconds_for_job = max(
                PROCESS_TIMEOUT_SECONDS,
                (audio_duration_ms / 1000.0) * AUDIO_TIMEOUT_MULTIPLIER
            )

            elapsed_seconds = (now_utc - process_started_at_dt).total_seconds()

            if elapsed_seconds > timeout_seconds_for_job:
                logger.info(f"Job {job_data.job_id} timed out. Elapsed: {elapsed_seconds:.2f}s, Timeout: {timeout_seconds_for_job:.2f}s. Updating status to 'failed'.")
                timed_out_jobs_batch.update(job_snap.reference, {
                    "status": "failed",
                    "error_message": f"Processing timed out after {timeout_seconds_for_job:.0f} seconds (checked on job list).",
                    "process_ended_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                updates_count += 1
                if updates_count >= 499: # Firestoreのバッチ書き込み上限に近い
                    logger.info("Committing a batch of timed out job updates (reaching limit).")
                    timed_out_jobs_batch.commit()
                    timed_out_jobs_batch = db.batch() # 新しいバッチを開始
                    updates_count = 0

        except Exception as e:
            logger.error(f"Error processing job {job_snap.id} for timeout check: {e}", exc_info=True)
            continue # 次のジョブへ

    if updates_count > 0:
        logger.info(f"Committing final batch of {updates_count} timed out job updates.")
        timed_out_jobs_batch.commit()
    elif updates_count == 0 and timed_out_jobs_batch._document_references: # バッチに何かあるが updates_count が0 の場合（通常ないはず）
        logger.info("Committing batch with no counted updates (edge case).")
        timed_out_jobs_batch.commit()


@router.get("/whisper/jobs")
async def list_jobs(
    request: Request,
    background_tasks: BackgroundTasks, # BackgroundTasks を依存性として追加
    status: str | None = None,
    tag: str | None = None,
    limit: int = 100,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """ログインユーザー自身のジョブを一覧取得。取得前にタイムアウトジョブのステータスを更新する。"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )

        user_email = current_user.get("email")
        if not user_email:
            logger.error(f"User email not found in current_user for user_id: {current_user.get('uid')}")
            raise HTTPException(status_code=400, detail="User email not found.")

        db = firestore.Client()

        # ② 時間経過しすぎたlauncedとprocessingについてfailedにする
        # --- タイムアウトジョブのチェックと更新 ---
        # ここでは全ユーザーの processing ジョブをチェックする (必要に応じて current_user["uid"] で絞る)
        # この処理は list_jobs のレスポンスに影響を与えるため、非同期にする場合は注意が必要
        # ユーザーの指示に基づき、このステップは現在のユーザーに限定せず、システム全体で実行されるように見えます。
        await check_and_update_timeout_jobs(db)
        # --- タイムアウトジョブのチェックと更新 ここまで ---

        # --- キューイングされているジョブの処理トリガー ---
        try:
            current_processing_count = _get_current_processing_job_count() # whisper_batch.py の関数を利用
            max_processing_jobs = int(_get_env_var("MAX_PROCESSING_JOBS", "5")) # whisper_batch.py の関数を利用

            if current_processing_count < max_processing_jobs:
                logger.info(f"Processing slots available ({current_processing_count}/{max_processing_jobs}). Checking for queued jobs for user {user_email}.")
                # 現在のユーザーのキューイングジョブを取得
                # システム全体で空きがあれば他のユーザーのジョブも処理する方針の場合、
                # user_id によるフィルタリングを外すか、別途システム全体のキューを確認するロジックを追加検討。
                # ここでは、まず現在のユーザーの queued または launched ジョブから処理を試みる。
                queued_jobs_query = (
                    db.collection(WHISPER_JOBS_COLLECTION)
                    .where(filter=FieldFilter("user_email", "==", user_email)) # user_id から user_email に変更
                    .where(filter=FieldFilter("status", "in", ["queued", "launched"]))
                    .order_by("created_at", direction=Query.ASCENDING) # upload_at から created_at に変更 (FirestoreDataモデルに準拠)
                    .limit(max_processing_jobs - current_processing_count) # 利用可能なスロット数分だけ取得
                )
                
                queued_job_snapshots = list(queued_jobs_query.stream())

                if queued_job_snapshots:
                    for job_snap in queued_job_snapshots:
                        job_id_to_trigger = job_snap.id
                        logger.info(f"Attempting to trigger batch processing for queued job {job_id_to_trigger} via list_jobs API call.")
                        # trigger_whisper_batch_processing は内部でジョブの現在のステータスを再確認し、
                        # 必要であればステータスを 'launched' に更新してGCP Batchジョブの作成をスケジュールします。
                        background_tasks.add_task(trigger_whisper_batch_processing, job_id_to_trigger, background_tasks)
                else:
                    logger.info(f"No queued or launched jobs found for user {user_email} to trigger at this moment via list_jobs API call.")
            else:
                logger.info(f"Max processing jobs ({max_processing_jobs}) reached. No new 'queued' or 'launched' jobs triggered via list_jobs API call for user {user_email}.")
        except Exception as e:
            logger.error(f"Error during queued job trigger in list_jobs API call for user {user_email}: {e}", exc_info=True)
        # --- キューイングされているジョブの処理トリガー ここまで ---

        # ④ ②又は③の処理があった場合は再度①と同様にデータを吸い出し、なければ①で得たデータ（一覧）について、一覧としてfrontendに返す。
        # Firestoreからデータを取得 (①の処理)
        col = db.collection(WHISPER_JOBS_COLLECTION)
        
        # 自分のemailに一致するもの
        q = col.where(filter=FieldFilter("user_email", "==", user_email))
        
        # .envにある環境変数FIRESTORE_MAX_DAYS日前までにupdateしたデータ一覧を取得
        min_update_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=FIRESTORE_MAX_DAYS)
        q = q.where(filter=FieldFilter("updated_at", ">=", min_update_date))

        if status:
            allowed = set(status.split(",")).intersection(VALID_STATUSES)
            if allowed:
                q = q.where(filter=FieldFilter("status", "in", list(allowed)))
        if tag:
            q = q.where(filter=FieldFilter("tags", "array_contains", tag))
        q = q.order_by("updated_at", direction=firestore.Query.DESCENDING).limit(limit)
        docs_snapshot = q.stream()
        
        # to_dict() と id の追加
        docs_list = []
        for d in docs_snapshot:
            doc_dict = d.to_dict()
            if doc_dict: # ドキュメントが存在することを確認
                doc_dict["id"] = d.id
                docs_list.append(doc_dict)
        
        return create_dict_logger(
            {"jobs": docs_list},
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )
    except Exception as e:
        logger.exception("ジョブ一覧取得エラー")
        return JSONResponse(status_code=500, content={"detail": f"ジョブ一覧取得エラー: {str(e)}"})

@router.get("/whisper/jobs/{file_hash}")
async def get_job(
    request: Request,
    file_hash: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """ハッシュ値を指定して特定のジョブ詳細を取得"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )

        db = firestore.Client()
        col = db.collection(WHISPER_JOBS_COLLECTION)
        q = col.where(filter=FieldFilter("file_hash", "==", file_hash)).where(
            filter=FieldFilter("user_id", "==", current_user["uid"])
        )
        doc = next(iter(q.stream()), None)
        
        if not doc:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")
        
        job_data = doc.to_dict() | {"id": doc.id}
        
        return create_dict_logger(
            job_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ジョブ詳細取得エラー: {file_hash}")
        return JSONResponse(status_code=500, content={"detail": f"ジョブ詳細取得エラー: {str(e)}"})

def _update_job_status(
    db: firestore.Client,
    file_hash: str,
    user_id: str,
    new_status: str,
) -> str:
    """ジョブステータスを更新する内部関数"""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"無効なステータス: {new_status}")
        
    col = db.collection(WHISPER_JOBS_COLLECTION)
    q = col.where(filter=FieldFilter("file_hash", "==", file_hash)).where(
        filter=FieldFilter("user_id", "==", user_id)
    )
    snap = next(iter(q.stream()), None)
    if not snap:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    # トランザクションの適切な使い方
    transaction = db.transaction()
    
    @firestore.transactional
    def update_transaction(transaction, ref):
        doc_snapshot = ref.get(transaction=transaction)
        if not doc_snapshot.exists:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")
            
        data = doc_snapshot.to_dict()
        if data["status"] == new_status:
            return  # 既に同じステータスなら何もしない
            
        # ビジネスルール
        if new_status == "canceled" and data["status"] != "queued":
            raise HTTPException(400, "queued のジョブのみキャンセルできます")
        if new_status == "queued" and data["status"] not in {"completed", "failed", "canceled"}:
            raise HTTPException(400, "retry できる状態ではありません")

        transaction.update(ref, {"status": new_status, "updated_at": firestore.SERVER_TIMESTAMP})
    
    try:
        update_transaction(transaction, snap.reference)
    except firestore.TransactionFailed as e:
        raise HTTPException(status_code=409, detail="ステータス更新に失敗しました") from e
        
    return snap.id

@router.post("/whisper/jobs/{file_hash}/cancel")
async def cancel_job(
    request: Request,
    file_hash: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """キュー待ち中のジョブをキャンセルする"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )
        
        db = firestore.Client()
        job_id = _update_job_status(db, file_hash, current_user["uid"], "canceled")
        
        response_data = {"status": "canceled", "job_id": job_id, "file_hash": file_hash}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ジョブキャンセルエラー: {file_hash}")
        return JSONResponse(status_code=500, content={"detail": f"ジョブキャンセルエラー: {str(e)}"})

@router.post("/whisper/jobs/{file_hash}/edit")
async def edit_job_transcript(
    request: Request,
    file_hash: str,
    edit_request: WhisperEditRequest, # リクエストボディを受け取る
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """特定ジョブの文字起こし結果を編集してGCSに保存する"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )
        user_id = current_user["uid"]

        db = firestore.Client()
        col_ref = db.collection(WHISPER_JOBS_COLLECTION)
        
        # file_hashとuser_idでドキュメントを検索
        query = col_ref.where(filter=FieldFilter("file_hash", "==", file_hash)).where(
            filter=FieldFilter("user_id", "==", user_id)
        )
        docs = list(query.limit(1).stream())

        if not docs:
            logger.warning(f"編集対象のジョブが見つかりません: file_hash={file_hash}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="編集対象のジョブが見つかりません")

        job_doc_ref = docs[0].reference
        job_id = docs[0].id # ログ出力用
        
        # 編集された文字起こし結果をGCSに保存
        segments_data = [segment.model_dump() for segment in edit_request.segments]
        
        # GCSへの保存パスを生成 ({file_hash}/edited_transcript.json)
        edited_transcript_blob_name = f"{file_hash}/edited_transcript.json"
        
        # GCSに保存
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(edited_transcript_blob_name)
        
        # JSONとして保存
        json_content = json.dumps(segments_data, ensure_ascii=False, indent=2)
        blob.upload_from_string(json_content, content_type='application/json')
        
        logger.info(f"編集された文字起こし結果をGCSに保存しました: gs://{GCS_BUCKET_NAME}/{edited_transcript_blob_name}")
        
        # Firestoreのupdated_atのみ更新（segmentsは保存しない）
        job_doc_ref.update({
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        
        logger.info(f"ジョブ {job_id} (hash: {file_hash}) の文字起こしを更新しました。")
        response_data = {
            "status": "success", 
            "message": "文字起こし結果を更新しました", 
            "file_hash": file_hash, 
            "job_id": job_id,
            "gcs_path": f"gs://{GCS_BUCKET_NAME}/{edited_transcript_blob_name}"
        }
        
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )

    except HTTPException as he:
        # ログに詳細情報を残す
        logger.error(f"ジョブ編集HTTPエラー ({he.status_code}): {he.detail} for file_hash={file_hash}", exc_info=True)
        raise he
    except Exception as e:
        logger.exception(f"ジョブ編集中の予期せぬエラー: file_hash={file_hash}")
        return JSONResponse(status_code=500, content={"detail": f"ジョブ編集エラー: {str(e)}"})

@router.post("/whisper/jobs/{file_hash}/retry")
async def retry_job(
    request: Request,
    file_hash: str,
    background_tasks: BackgroundTasks, # Add BackgroundTasks
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """完了/失敗/キャンセル済みのジョブを再キューし、バッチ処理を再トリガーする"""
    try:
        # ... (log_request logic) ...
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )
        user_id = current_user["uid"]

        db_client = firestore.Client() # Explicitly create client or use global
        col_ref = db_client.collection(WHISPER_JOBS_COLLECTION)
        
        # Find the job by file_hash and user_id
        query = col_ref.where(filter=FieldFilter("file_hash", "==", file_hash)).where(
            filter=FieldFilter("user_id", "==", user_id)
        ).limit(1) # Assuming one job per file_hash for a user, or take the latest.
        
        docs = list(query.stream())
        if not docs:
            raise HTTPException(status_code=404, detail="Retry target job not found.")
        
        job_doc_ref = docs[0].reference
        job_id_to_retry = docs[0].id
        current_job_status = docs[0].to_dict().get("status")

        # Business rule: only retry from terminal states
        if current_job_status not in {"completed", "failed", "canceled"}:
            raise HTTPException(status_code=400, detail=f"Job in status '{current_job_status}' cannot be retried now.")

        # Update status to 'queued'
        job_doc_ref.update({
            "status": "queued",
            "updated_at": firestore.SERVER_TIMESTAMP,
            "error_message": None, # Clear previous error
            "process_started_at": None,
            "process_ended_at": None
            # segments might be cleared or kept depending on desired retry behavior
        })
        logger.info(f"Job {job_id_to_retry} (hash: {file_hash}) status updated to 'queued' for retry.")

        # Trigger batch processing again
        background_tasks.add_task(trigger_whisper_batch_processing, job_id_to_retry, background_tasks)
        logger.info(f"Scheduled batch processing re-trigger for job {job_id_to_retry}.")

        response_data = {"status": "queued_for_retry", "job_id": job_id_to_retry, "file_hash": file_hash}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ジョブ再キューエラー: {file_hash}")
        return JSONResponse(status_code=500, content={"detail": f"ジョブ再キューエラー: {str(e)}"})

@router.get("/whisper/transcript/{file_hash}/original")
async def get_original_transcript(
    request: Request,
    file_hash: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """元の文字起こし結果（combine.json）をGCSから取得"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )
        user_id = current_user["uid"]

        # ユーザーの権限確認：file_hashに対応するジョブが存在し、そのユーザーのものかチェック
        db = firestore.Client()
        col = db.collection(WHISPER_JOBS_COLLECTION)
        q = col.where(filter=FieldFilter("file_hash", "==", file_hash)).where(
            filter=FieldFilter("user_id", "==", user_id)
        )
        doc = next(iter(q.stream()), None)
        
        if not doc:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")

        # GCSから元の文字起こし結果を取得
        combine_blob_name = f"{file_hash}/combine.json"
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(combine_blob_name)
        
        if not blob.exists():
            raise HTTPException(status_code=404, detail="文字起こし結果が見つかりません")
        
        # JSONデータを取得
        json_content = blob.download_as_text()
        segments_data = json.loads(json_content)
        
        logger.info(f"元の文字起こし結果を返しました: {file_hash}")
        return segments_data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"元の文字起こし結果取得エラー: {file_hash}")
        return JSONResponse(status_code=500, content={"detail": f"文字起こし結果取得エラー: {str(e)}"})

@router.get("/whisper/transcript/{file_hash}/edited")
async def get_edited_transcript(
    request: Request,
    file_hash: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """編集済み文字起こし結果（edited_transcript.json）をGCSから取得"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )
        user_id = current_user["uid"]

        # ユーザーの権限確認：file_hashに対応するジョブが存在し、そのユーザーのものかチェック
        db = firestore.Client()
        col = db.collection(WHISPER_JOBS_COLLECTION)
        q = col.where(filter=FieldFilter("file_hash", "==", file_hash)).where(
            filter=FieldFilter("user_id", "==", user_id)
        )
        doc = next(iter(q.stream()), None)
        
        if not doc:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")

        # GCSから編集済み文字起こし結果を取得
        edited_blob_name = f"{file_hash}/edited_transcript.json"
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(edited_blob_name)
        
        if not blob.exists():
            raise HTTPException(status_code=404, detail="編集済み文字起こし結果が見つかりません")
        
        # JSONデータを取得
        json_content = blob.download_as_text()
        segments_data = json.loads(json_content)
        
        logger.info(f"編集済み文字起こし結果を返しました: {file_hash}")
        return segments_data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"編集済み文字起こし結果取得エラー: {file_hash}")
        return JSONResponse(status_code=500, content={"detail": f"文字起こし結果取得エラー: {str(e)}"})
