# API ルート: whisper.py - Whisper音声文字起こし関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import os, json, io, base64, hashlib, math, datetime, uuid
from pydub import AudioSegment
from google.cloud import storage, pubsub_v1, firestore
from google.cloud.firestore_v1 import FieldFilter
from functools import partial

from app.api.auth import get_current_user
from common_utils.logger import logger, create_dict_logger, log_request
from common_utils.class_types import WhisperUploadRequest, WhisperFirestoreData, WhisperPubSubMessageData, WhisperSegment, WhisperEditRequest

# Import the new batch processing trigger function
from app.api.whisper_batch import trigger_whisper_batch_processing

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 設定値の読み込み
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCS_BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
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

router = APIRouter()

# 有効なステータス一覧
VALID_STATUSES = {"queued", "processing", "completed", "failed", "canceled"}

# 辞書ロガーのセットアップ
create_dict_logger = partial(create_dict_logger, sensitive_keys=SENSITIVE_KEYS)

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

        # Base64データのバリデーション
        if not whisper_request.audio_data:
            return JSONResponse(status_code=400, content={"detail": "音声データが提供されていません"})

        if not whisper_request.audio_data.startswith("data:"):
            return JSONResponse(status_code=400, content={"detail": "無効な音声データ形式です"})

        # MIMEタイプの取得
        mime_parts: List[str] = whisper_request.audio_data.split(";")[0].split(":")
        if len(mime_parts) < 2:
            return JSONResponse(status_code=400, content={"detail": "無効なMIMEタイプ形式"})

        mime_type: str = mime_parts[1]
        if not mime_type.startswith("audio/"):
            return JSONResponse(status_code=400, content={"detail": f"無効な音声フォーマット: {mime_type}"})

            # Base64データのデコード前にサイズチェック
        try:
            base64_data = whisper_request.audio_data.split(",")[1]
            if len(base64_data) > MAX_AUDIO_BASE64_CHARS:
                return JSONResponse(status_code=413, content={"detail": f"音声データが大きすぎます（最大{MAX_AUDIO_BASE64_CHARS/1024/1024:.1f}MB）"})
                
            audio_content: bytes = base64.b64decode(base64_data)
            
            # ファイルサイズチェック
            if len(audio_content) > WHISPER_MAX_BYTES:
                return JSONResponse(status_code=413, content={"detail": f"音声ファイルが大きすぎます（最大{WHISPER_MAX_BYTES/1024/1024:.1f}MB）"})
        except Exception:
            return JSONResponse(status_code=400, content={"detail": "Base64デコードに失敗しました"})

        # より強力なハッシュアルゴリズムを使用
        file_hash: str = hashlib.sha256(audio_content).hexdigest()

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
        # 音声ファイルのサイズを取得 (バイト単位)
        audio_size: int = len(audio_content)
        
        try:
            # メモリ上でファイルを処理
            audio_file = io.BytesIO(audio_content)
            
            # MIMEタイプに応じて適切な形式でロード
            if mime_type in ["audio/mp3", "audio/mpeg"]:
                audio = AudioSegment.from_mp3(audio_file)
            elif mime_type == "audio/wav":
                audio = AudioSegment.from_wav(audio_file)
            elif mime_type == "audio/ogg":
                audio = AudioSegment.from_ogg(audio_file)
            elif mime_type in ["audio/m4a", "audio/x-m4a"]:
                audio = AudioSegment.from_file(audio_file, format="m4a")
            elif mime_type == "audio/aac":
                audio = AudioSegment.from_file(audio_file, format="aac")
            elif mime_type == "audio/webm":
                audio = AudioSegment.from_file(audio_file, format="webm")
            else:
                # 未知の形式の場合はデフォルトで処理
                audio = AudioSegment.from_file(audio_file)
            
            # 長さをミリ秒単位で取得
            audio_duration_ms = len(audio)  # ミリ秒単位で取得
            logger.debug(f"音声長さ: {audio_duration_ms} ms")
            
            # 音声の長さチェック（秒単位に変換）
            if audio_duration_ms > WHISPER_MAX_SECONDS * 1000:
                return JSONResponse(
                    status_code=413, 
                    content={"detail": f"音声の長さが制限を超えています（最大{WHISPER_MAX_SECONDS/60:.1f}分）"}
                )
            
        except Exception as e:
            logger.error("音声長さの取得に失敗しました: %s", str(e))
            return JSONResponse(status_code=400, content={"detail": "音声長さの取得に失敗しました"})
        
        # Determine GCS paths
        user_id: str = current_user["uid"]
        # file_hash is already calculated: e.g., file_hash: str = hashlib.sha256(audio_content).hexdigest()
        # audio_file_extension is determined: e.g., .mp3

        gcs_path_prefix = f"whisper/{user_id}/{file_hash}"
        
        # 環境変数からファイル名テンプレートを使用
        file_ext = audio_file_extension.lstrip(".")
        original_audio_gcs_filename = os.environ["WHISPER_AUDIO_BLOB"].format(file_hash=file_hash, ext=file_ext)
        audio_gcs_full_path = f"{gcs_path_prefix}/{original_audio_gcs_filename}"
        
        # Path for the final combined transcript from whisper_batch/app/main.py
        # 環境変数からcombineファイル名テンプレートを使用
        transcription_output_gcs_filename = os.environ["WHISPER_COMBINE_BLOB"].format(file_hash=file_hash)
        transcription_gcs_full_path = f"{gcs_path_prefix}/{transcription_output_gcs_filename}"


        # GCSクライアントの設定
        storage_client_instance: storage.Client = storage.Client() # Renamed to avoid conflict if storage is imported module
        bucket = storage_client_instance.bucket(GCS_BUCKET_NAME)
        
        # 音声ファイルのアップロード (using audio_gcs_full_path)
        blob = bucket.blob(audio_gcs_full_path) # Use the determined full path
        blob.upload_from_string(audio_content, content_type=mime_type)
        logger.info(f"Uploaded original audio to gs://{GCS_BUCKET_NAME}/{audio_gcs_full_path}")

        # Firestoreにジョブ情報を記録
        job_id: str = str(uuid.uuid4()) # server-generated unique ID
        timestamp = firestore.SERVER_TIMESTAMP

        whisper_job_data = WhisperFirestoreData(
            job_id=job_id,
            user_id=user_id,
            user_email=current_user.get("email", ""), # Ensure email is correctly fetched
            filename=whisper_request.filename,
            description=whisper_request.description,
            recording_date=whisper_request.recording_date,
            gcs_bucket_name=GCS_BUCKET_NAME,
            audio_duration_ms=audio_duration_ms, # Ensure this is populated
            audio_size=audio_size, # Ensure this is populated
            file_hash=file_hash,
            language=whisper_request.language,
            initial_prompt=whisper_request.initial_prompt,
            status="queued", # Initial status
            created_at=timestamp,
            updated_at=timestamp,
            tags=whisper_request.tags or [],
            num_speakers=whisper_request.num_speakers,
            min_speakers=whisper_request.min_speakers or 1, # Default if None
            max_speakers=whisper_request.max_speakers or 1, # Default if None
            # New GCS path fields
            audio_file_path=audio_gcs_full_path,
            transcription_file_path=transcription_gcs_full_path,
            # segments, error_message, process_started_at, process_ended_at, gcp_batch_job_name are None initially
        )

        db = firestore.Client()
        job_doc_ref = db.collection(WHISPER_JOBS_COLLECTION).document(job_id)
        job_doc_ref.set(whisper_job_data.model_dump())
        logger.info(f"Whisper job {job_id} queued in Firestore.")

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

@router.get("/whisper/jobs")
async def list_jobs(
    request: Request,
    status: str | None = None,          # 例: queued,completed
    tag: str | None = None,             # 例: "会議"
    limit: int = 100,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """ログインユーザー自身のジョブを一覧取得"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )

        db = firestore.Client()
        col = db.collection(WHISPER_JOBS_COLLECTION)
        q = col.where(filter=FieldFilter("user_id", "==", current_user["uid"]))

        # ステータス絞り込み
        if status:
            allowed = set(status.split(",")).intersection(VALID_STATUSES)
            if allowed:
                q = q.where(filter=FieldFilter("status", "in", list(allowed)))

        # タグ絞り込み
        if tag:
            q = q.where(filter=FieldFilter("tags", "array_contains", tag))

        # 更新日時 desc
        q = q.order_by("updated_at", direction=firestore.Query.DESCENDING).limit(limit)

        docs = [d.to_dict() | {"id": d.id} for d in q.stream()]
        
        return create_dict_logger(
            {"jobs": docs},
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
    """特定ジョブの文字起こし結果を編集する"""
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
        
        # Firestoreドキュメントを更新
        update_data = {
            "segments": [segment.model_dump() for segment in edit_request.segments], # Pydanticモデルを辞書に変換
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        job_doc_ref.update(update_data)
        
        logger.info(f"ジョブ {job_id} (hash: {file_hash}) の文字起こしを更新しました。")
        response_data = {"status": "success", "message": "文字起こし結果を更新しました", "file_hash": file_hash, "job_id": job_id}
        
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
            "process_ended_at": None,
            "gcp_batch_job_name": None, # Clear previous batch job name
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
