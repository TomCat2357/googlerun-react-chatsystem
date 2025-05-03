from __future__ import annotations

import datetime
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google.cloud import firestore, storage

# ── 外部ユーティリティ ─────────────────────────────
from convert_audio import convert_audio
from transcribe import transcribe_audio
from diarize import diarize_audio
from combine_results import combine_results

# ── .env 読み込み ────────────────────────────────
load_dotenv("config/.env", override=True)

# ── 環境変数（未設定時は KeyError を発生させる） ───────────────────────────────────
COLLECTION: str = os.environ["WHISPER_JOBS_COLLECTION"]
PROCESS_TIMEOUT_SECONDS: int = int(os.environ["PROCESS_TIMEOUT_SECONDS"])
DURATION_TIMEOUT_FACTOR: float = float(os.environ["AUDIO_TIMEOUT_MULTIPLIER"])
POLL_INTERVAL_SECONDS: int = int(os.environ["POLL_INTERVAL_SECONDS"])
HF_AUTH_TOKEN: str = os.environ["HF_AUTH_TOKEN"]
DEVICE: str = os.environ["DEVICE"].lower()
USE_GPU: bool = DEVICE == "cuda"
TMP_ROOT: Path = Path(os.environ["LOCAL_TMP_DIR"])


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _log(msg: str, level: str = "INFO") -> None:
    ts = _utcnow().isoformat(timespec="seconds")
    out = sys.stderr if level.upper() == "ERROR" else sys.stdout
    print(f"{ts} [{level}] {msg}", file=out, flush=True)


def _mark_timeout_jobs(db: firestore.Client) -> None:
    now = _utcnow()
    col = db.collection(COLLECTION)
    batch = db.batch()
    updated = False
    for snap in col.where("status", "==", "processing").stream():
        data = snap.to_dict()
        started_at = data.get("process_started_at")
        if not started_at:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=datetime.timezone.utc)
        duration_ms = data.get("audio_duration_ms") or 0
        timeout_sec = max(
            PROCESS_TIMEOUT_SECONDS,
            int(duration_ms/1000 * DURATION_TIMEOUT_FACTOR),
        )
        if (now - started_at).total_seconds() > timeout_sec:
            batch.update(
                snap.reference,
                {"status": "failed", "error_message": "timeout", "updated_at": firestore.SERVER_TIMESTAMP},
            )
            updated = True
    if updated:
        batch.commit()


def _pick_next_job(db: firestore.Client) -> Optional[Dict[str, Any]]:
    @firestore.transactional
    def _txn(tx: firestore.Transaction) -> Optional[Dict[str, Any]]:
        col = db.collection(COLLECTION)
        docs = (
            col.where("status", "==", "queued")
            .order_by("created_at")
            .limit(1)
            .stream(transaction=tx)
        )
        docs = list(docs)
        if not docs:
            return None
        doc = docs[0]
        tx.update(
            doc.reference,
            {
                "status": "processing",
                "process_started_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        data = doc.to_dict()
        data["job_id"] = doc.id
        return data
    return _txn(db.transaction())


def _process_job(db: firestore.Client, job: Dict[str, Any]) -> None:
    # 必須メタデータのチェック
    job_id = job.get("job_id")
    filename = job.get("filename")
    bucket = job.get("gcs_bucket_name")
    file_hash = job.get("file_hash")

    missing: List[str] = []
    if not job_id:
        missing.append("job_id")
    if not filename:
        missing.append("filename")
    if not bucket:
        missing.append("gcs_bucket_name")
    if not file_hash:
        missing.append("file_hash")

    if missing:
        msg = f"Required metadata missing: {', '.join(missing)}"
        _log(f"JOB {job_id or '<unknown>'} ✖ Metadata error: {msg}", level="ERROR")
        if job_id:
            db.collection(COLLECTION).document(job_id).update({
                "status": "failed",
                "error_message": msg,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
        return

    # ファイル拡張子と GCS パスの組み立て
    ext = Path(filename).suffix.lstrip(".").lower()
    audio_blob = f"{file_hash}_audio.{ext}"
    transcript_blob = f"{file_hash}_transcript.json"
    audio_uri = f"gs://{bucket}/{audio_blob}"
    transcript_uri = f"gs://{bucket}/{transcript_blob}"

    _log(f"JOB {job_id} ▶ Start (audio: {audio_uri})")

    tmp_dir = TMP_ROOT / f"job_{job_id}_{int(time.time())}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    storage_client = storage.Client()

    try:
        # ダウンロード
        local_audio = tmp_dir / audio_blob
        storage_client.bucket(bucket).blob(audio_blob).download_to_filename(local_audio)
        _log(f"JOB {job_id} ⤵ Downloaded → {local_audio}")

        # 変換
        wav_path = tmp_dir / f"{file_hash}_16k_mono.wav"
        convert_audio(str(local_audio), str(wav_path), use_gpu=USE_GPU)
        _log(f"JOB {job_id} 🎧 Converted → {wav_path}")

        # 文字起こし
        transcript_local = tmp_dir / transcript_blob
        transcribe_audio(str(wav_path), str(transcript_local), device=DEVICE)
        _log(f"JOB {job_id} ✍ Transcribed → {transcript_local}")

        # 話者分離
        diarization_local = tmp_dir / "speaker.json"
        diarize_audio(
            str(wav_path),
            str(diarization_local),
            hf_auth_token=HF_AUTH_TOKEN,
            num_speakers=job.get("num_speakers"),
            min_speakers=job.get("min_speakers", 1),
            max_speakers=job.get("max_speakers", 1),
            device=DEVICE,
        )
        _log(f"JOB {job_id} 👥 Diarized → {diarization_local}")

        # 結果結合
        final_local = tmp_dir / "final.json"
        combine_results(str(transcript_local), str(diarization_local), str(final_local))
        _log(f"JOB {job_id} 🔗 Combined → {final_local}")

        # アップロード
        storage_client.bucket(bucket).blob(transcript_blob).upload_from_filename(final_local)
        _log(f"JOB {job_id} ⬆ Uploaded → {transcript_uri}")

        # Firestore 更新
        db.collection(COLLECTION).document(job_id).update({
            "status": "completed",
            "result_json_uri": transcript_uri,
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        _log(f"JOB {job_id} ✔ Completed")

    except Exception as e:
        err = str(e)
        _log(f"JOB {job_id} ✖ Failed: {err}\n{traceback.format_exc()}", level="ERROR")
        db.collection(COLLECTION).document(job_id).update({
            "status": "failed",
            "error_message": err,
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    db = firestore.Client()
    while True:
        try:
            _mark_timeout_jobs(db)
            job = _pick_next_job(db)
            if job:
                _process_job(db, job)
            else:
                _log("キューが空です。待機…")
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            _log("SIGINT 受信。ワーカーを終了します", level="INFO")
            break
        except Exception as e:
            _log(f"Main loop error: {e}\n{traceback.format_exc()}", level="ERROR")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
