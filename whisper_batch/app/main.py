#!/usr/bin/env python
"""
Whisper Queue Worker

Firestore 上の whisper ジョブを順次処理するキュー仕組み。
処理中ジョブのタイムアウト監視 → Failed への切替え、
最古の queued を processing にしてパイプライン実行 → Completed/Failed 更新
を繰り返し、キューが空になれば終了します。
"""

import os
import sys
import time
import datetime
import traceback
import shutil
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import firestore, storage
from common_utils.class_types import WhisperFirestoreData

# --- モジュール読み込み（各処理は既存実装を使う） ---
from convert_audio    import main as convert_audio
from transcribe       import main as transcribe_audio
from diarize          import main as diarize_audio
from combine_results  import main as combine_results

# --- 設定読み込み (.env → override .env.develop) ---
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / ".env")
load_dotenv(BASE_DIR / "config_develop" / ".env.develop", override=True)

# --- 必須環境変数 ---
PROJECT_ID        = os.environ["GCP_PROJECT_ID"]
COLLECTION_NAME   = os.environ["WHISPER_JOBS_COLLECTION"]
HF_AUTH_TOKEN     = os.environ["HF_AUTH_TOKEN"]

# --- タイムアウト & ポーリング設定 ---
PROCESS_TIMEOUT_SECONDS  = int(os.environ.get("PROCESS_TIMEOUT_SECONDS", 300))
AUDIO_TIMEOUT_MULTIPLIER = float(os.environ.get("AUDIO_TIMEOUT_MULTIPLIER", 1.0))
POLL_INTERVAL_SECONDS    = int(os.environ.get("POLL_INTERVAL_SECONDS", 5))
LOCAL_TMP_DIR            = os.environ.get("LOCAL_TMP_DIR", "/tmp")

# --- GCP クライアント初期化 ---
db             = firestore.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)


def _utcnow() -> datetime.datetime:
    """UTC 現在時刻を timezone aware で返す"""
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)


def _log(msg: str, level: str = "INFO") -> None:
    """標準出力 or 標準エラーにタイムスタンプ付きログを出力"""
    ts = _utcnow().isoformat()
    out = sys.stderr if level == "ERROR" else sys.stdout
    print(f"{ts} [{level}] {msg}", file=out)


def _fail_stuck_jobs() -> None:
    """
    processing 状態でタイムアウト閾値を超えたジョブを failed に更新
    閾値 = max(PROCESS_TIMEOUT_SECONDS, audio_duration(ms)×AUDIO_TIMEOUT_MULTIPLIER)
    """
    now = _utcnow()
    q = db.collection(COLLECTION_NAME).where("status", "==", "processing")
    for doc in q.stream():
        data = doc.to_dict()
        started = data.get("process_started_at")
        if not started:
            continue

        # Firestore Timestamp → datetime
        started_dt = started.to_datetime() if hasattr(started, "to_datetime") else started
        elapsed = (now - started_dt).total_seconds()

        # 動的閾値計算 (秒)
        audio_ms = data.get("audio_duration", 0)
        audio_sec = audio_ms / 1000.0 * AUDIO_TIMEOUT_MULTIPLIER
        cutoff = max(PROCESS_TIMEOUT_SECONDS, audio_sec)

        if elapsed > cutoff:
            _log(f"Timeout → failed: {doc.id} (elapsed {elapsed:.0f}s > {cutoff:.0f}s)", level="ERROR")
            doc.reference.update({
                "status": "failed",
                "error_message": f"Timeout exceeded: waited {elapsed:.0f}s (threshold {cutoff:.0f}s)",
                "process_ended_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })


def _claim_next_job() -> WhisperFirestoreData | None:
    """
    トランザクションで最古の queued を processing に切替え、
    WhisperFirestoreData オブジェクトを返す。なければ None。
    """
    @firestore.transactional
    def txn(tx: firestore.Transaction):
        q = (db.collection(COLLECTION_NAME)
               .where("status", "==", "queued")
               .order_by("created_at")
               .limit(1))
        docs = list(q.stream(transaction=tx))
        if not docs:
            return None

        doc = docs[0]
        tx.update(doc.reference, {
            "status": "processing",
            "process_started_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        updated_data = doc.to_dict()
        updated_data.update({
            "status": "processing",
            "process_started_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow(),
        })
        return WhisperFirestoreData(**updated_data)

    return txn(db.transaction())


def _upload_text(bucket_name: str, path: str, text: str) -> None:
    """文字起こし結果を GCS にアップロード"""
    blob = storage_client.bucket(bucket_name).blob(path)
    blob.upload_from_string(text, content_type="text/plain; charset=utf-8")


def _process_job(job: WhisperFirestoreData) -> None:
    """実際の音声変換・文字起こし・話者分離・統合パイプライン実行 & 結果反映"""
    workdir = Path(LOCAL_TMP_DIR) / job.job_id
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        _log(f"Processing start: {job.job_id}")

        # 1) GCS → ローカルへ音声ダウンロード
        local_audio = workdir / Path(job.audio_file_path).name
        storage_client.bucket(job.gcs_bucket_name) \
                      .blob(job.audio_file_path) \
                      .download_to_filename(str(local_audio))
        _log(f"Downloaded audio to {local_audio}")

        # 2) convert_audio
        wav_path = convert_audio(str(local_audio), workdir=str(workdir))

        # 3) transcribe
        stt_json = transcribe_audio(
            str(wav_path),
            language=job.language,
            initial_prompt=job.initial_prompt,
            hf_token=HF_AUTH_TOKEN,
        )

        # 4) diarize
        diarized = diarize_audio(
            stt_json,
            num_speakers=job.num_speakers,
            min_speakers=job.min_speakers,
            max_speakers=job.max_speakers,
        )

        # 5) combine_results
        transcript = combine_results(diarized)

        # 成功: GCS & Firestore 更新
        _upload_text(job.gcs_bucket_name, job.transcription_file_path, transcript)
        db.collection(COLLECTION_NAME).document(job.job_id).update({
            "status": "completed",
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        _log(f"Completed: {job.job_id}")

    except Exception as e:
        tb = traceback.format_exc(limit=2)
        _log(f"Failed: {job.job_id}\n{e}\n{tb}", level="ERROR")
        db.collection(COLLECTION_NAME).document(job.job_id).update({
            "status": "failed",
            "error_message": tb,
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

    finally:
        # 作業ディレクトリをクリーンアップ
        shutil.rmtree(str(workdir), ignore_errors=True)


def main() -> None:
    _log("Whisper Queue Worker started")

    while True:
        # ① processing stuck ジョブを failed に
        _fail_stuck_jobs()

        # ② queued の次ジョブを取得 → なければ終了
        job = _claim_next_job()
        if job is None:
            _log("No queued jobs. Exiting.")
            break

        # ③ パイプライン実行
        _process_job(job)

        # 過負荷防止に少し待機
        time.sleep(POLL_INTERVAL_SECONDS)

    _log("Whisper Queue Worker finished")


if __name__ == "__main__":
    main()
