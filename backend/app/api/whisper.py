# API ルート: whisper.py - Whisper音声文字起こし関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import os, json, io, base64, hashlib, math, datetime
from pydub import AudioSegment
from google.cloud import storage, pubsub_v1, firestore
from google.cloud.firestore_v1 import FieldFilter
from functools import partial

from app.api.auth import get_current_user
from common_utils.logger import logger, create_dict_logger, log_request
from common_utils.class_types import WhisperUploadRequest, WhisperFirestoreData, WhisperPubSubMessageData

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

router = APIRouter()

# 有効なステータス一覧
VALID_STATUSES = {"queued", "processing", "completed", "failed", "canceled"}

# 辞書ロガーのセットアップ
create_dict_logger = partial(create_dict_logger, sensitive_keys=SENSITIVE_KEYS)

@router.post("/whisper")
async def upload_audio(
    request: Request, 
    whisper_request: WhisperUploadRequest,
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

        # Base64データのデコード
        try:
            audio_content: bytes = base64.b64decode(whisper_request.audio_data.split(",")[1])
        except Exception:
            return JSONResponse(status_code=400, content={"detail": "Base64デコードに失敗しました"})

        # ファイルのハッシュ値を計算
        file_hash: str = hashlib.md5(audio_content).hexdigest()

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
            audio_duration = int(math.ceil(len(audio) / 1000))
            logger.debug(f"音声長さ: {audio_duration} 秒")
            
        except Exception as e:
            logger.error("音声長さの取得に失敗しました: %s", str(e))
            return JSONResponse(status_code=400, content={"detail": "音声長さの取得に失敗しました"})
        
        # GCSのパス設定
        storage_client: storage.Client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        base_dir: str = f"whisper/{user_id}/{file_hash}"
        
        # 音声ファイルのアップロード
        blob = bucket.blob(f"{base_dir}/origin{audio_file_extension}")
        blob.upload_from_string(audio_content, content_type=mime_type)

        # Firestoreにジョブ情報を記録
        # リクエストIDをそのままjob_idに使う。一意なので問題なし
        job_id: str = request_info['X-Request-Id']
        timestamp = firestore.SERVER_TIMESTAMP

        # 音声ファイルパスと文字起こしファイルパスを設定
        audio_file_path = f"{base_dir}/origin{audio_file_extension}"
        transcription_file_path = ""

        # ジョブデータの作成
        whisper_job: WhisperFirestoreData = WhisperFirestoreData(
            job_id=job_id,
            user_id=user_id,
            user_email=user_email,
            filename=whisper_request.filename,
            description=whisper_request.description,
            recording_date=whisper_request.recording_date,
            gcs_bucket_name=GCS_BUCKET_NAME,
            audio_file_path=audio_file_path,
            transcription_file_path=transcription_file_path,
            audio_duration=audio_duration,
            audio_size=audio_size,
            file_hash=file_hash,
            language=whisper_request.language or "ja",
            initial_prompt=whisper_request.initial_prompt or "",
            status="queued",
            created_at=timestamp,
            updated_at=timestamp,
            process_started_at=None,
            process_ended_at=None,
            tags=whisper_request.tags,
            error_message=None,
            # 話者数パラメータを追加
            num_speakers=whisper_request.num_speakers,
            min_speakers=whisper_request.min_speakers or 1,
            max_speakers=whisper_request.max_speakers or 1,
        )

        # Firestoreに保存
        db = firestore.Client()
        db.collection(WHISPER_JOBS_COLLECTION).document(job_id).set(whisper_job.model_dump())

        # Pub/Subに通知
        publisher: pubsub_v1.PublisherClient = pubsub_v1.PublisherClient()
        topic_path: str = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC)

        # ISO 8601形式の現在時刻を生成
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

        message_data = WhisperPubSubMessageData(
            job_id=job_id,
            event_type="new_job",
            timestamp=current_time
        )

        message_bytes: bytes = json.dumps(message_data).encode("utf-8")
        publish_future: pubsub_v1.publisher.futures.Future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()
        
        response_data = {"status": "success", "job_id": job_id, "file_hash": file_hash}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERAL_LOG_MAX_LENGTH,
        )

    except Exception as e:
        logger.exception("音声アップロードエラー")
        return JSONResponse(status_code=500, content={"detail": f"アップロードエラー: {str(e)}"})

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

    def txn(transaction, ref):
        data = ref.get(transaction=transaction).to_dict()
        if data["status"] == new_status:
            return  # 既に同じステータスなら何もしない
            
        # ビジネスルール
        if new_status == "canceled" and data["status"] != "queued":
            raise HTTPException(400, "queued のジョブのみキャンセルできます")
        if new_status == "queued" and data["status"] not in {"completed", "failed", "canceled"}:
            raise HTTPException(400, "retry できる状態ではありません")

        transaction.update(ref, {"status": new_status, "updated_at": firestore.SERVER_TIMESTAMP})

    db.transaction()(txn)(snap.reference)
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

@router.post("/whisper/jobs/{file_hash}/retry")
async def retry_job(
    request: Request,
    file_hash: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """完了/失敗/キャンセル済みのジョブを再キューする"""
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, GENERAL_LOG_MAX_LENGTH
        )
        
        db = firestore.Client()
        job_id = _update_job_status(db, file_hash, current_user["uid"], "queued")
        
        response_data = {"status": "queued", "job_id": job_id, "file_hash": file_hash}
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
