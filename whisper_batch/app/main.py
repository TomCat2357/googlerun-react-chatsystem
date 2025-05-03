"""
whisper_batch/app/main.py ― Whisper Batch Worker (revised 2025-05-03)

Queued → processing → completed/failed のバッチワーカー。
Firestore のスキーマ差異・環境差異を自己吸収できるよう改修。
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google.cloud import firestore, storage

# ── 外部ユーティリティ ─────────────────────────────
from convert_audio import convert_audio
from transcribe import transcribe_audio
from diarize import diarize_audio
from combine_results import combine_results

# ── .env 読み込み ────────────────────────────────
load_dotenv("config/.env", override=True)

# ── 環境変数（複数名称をフォールバックで吸収） ──
COLLECTION: str = (
    os.getenv("WHISPER_COLLECTION")
    or os.getenv("WHISPER_JOBS_COLLECTION")
    or "whisper_jobs"
)

PROCESS_TIMEOUT_SECONDS: int = int(os.getenv("PROCESS_TIMEOUT_SECONDS", "300"))
DURATION_TIMEOUT_FACTOR: float = float(
    os.getenv("DURATION_TIMEOUT_FACTOR")
    or os.getenv("AUDIO_TIMEOUT_MULTIPLIER")
    or "1.5"
)

POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))

# 音声アップロード先バケット（結果も同じバケットに格納）
GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME")
if not GCS_BUCKET_NAME:
    sys.stderr.write("[FATAL] GCS_BUCKET_NAME が未設定です。\n")
    sys.exit(1)

# HuggingFace トークン必須（PyAnnote）
HF_AUTH_TOKEN: Optional[str] = os.getenv("HF_AUTH_TOKEN")
if not HF_AUTH_TOKEN:
    sys.stderr.write(
        "[FATAL] HF_AUTH_TOKEN が未設定です。話者分離パイプラインが初期化できません。\n"
    )
    sys.exit(1)

# デバイス設定
DEVICE: str = os.getenv("DEVICE", "cuda").lower()
USE_GPU: bool = DEVICE == "cuda"

# 一時ディレクトリ
TMP_ROOT: Path = Path(os.getenv("TMP_ROOT") or os.getenv("LOCAL_TMP_DIR", "/tmp"))

# ── 共通ユーティリティ ─────────────────────────────
def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _log(msg: str, level: str = "INFO") -> None:
    ts = _utcnow().isoformat(timespec="seconds")
    out = sys.stderr if level.upper() == "ERROR" else sys.stdout
    print(f"{ts} [{level}] {msg}", file=out, flush=True)


# ── Firestore タイムアウト判定 ─────────────────────
def _mark_timeout_jobs(db: firestore.Client) -> None:
    """processing 状態でタイムアウトしたジョブを failed へ"""
    now = _utcnow()
    col = db.collection(COLLECTION)
    batch = db.batch()
    updated = False

    for snap in col.where("status", "==", "processing").stream():
        data = snap.to_dict()
        started_at: Optional[datetime.datetime] = data.get("process_started_at")
        if not started_at:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=datetime.timezone.utc)

        duration_ms = (
            data.get("audio_duration_ms")
            or data.get("audio_duration")
            or 0
        )
        timeout_sec = max(
            PROCESS_TIMEOUT_SECONDS, int(duration_ms / 1000 * DURATION_TIMEOUT_FACTOR)
        )

        if (now - started_at).total_seconds() > timeout_sec:
            batch.update(
                snap.reference,
                {
                    "status": "failed",
                    "error": "timeout",
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
            )
            updated = True

    if updated:
        batch.commit()


# ── 次ジョブ取得（Transactional） ──────────────────
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
        data["id"] = doc.id
        return data

    return _txn(db.transaction())


# ── 個別ジョブ処理 ────────────────────────────────
def _resolve_audio_uri(job: Dict[str, Any]) -> str:
    """audio_gcs_uri または (bucket + path) から完全 URI を生成"""
    if "audio_gcs_uri" in job:
        return job["audio_gcs_uri"]
    if "gcs_bucket_name" in job and "audio_file_path" in job:
        return f"gs://{job['gcs_bucket_name']}/{job['audio_file_path']}"
    raise KeyError("audio_gcs_uri または gcs_bucket_name+audio_file_path がありません")


def _process_job(db: firestore.Client, job: Dict[str, Any]) -> None:
    job_id = job["id"]
    try:
        audio_uri = _resolve_audio_uri(job)
    except Exception as e:
        _log(f"JOB {job_id} ✖ Metadata error: {e}", level="ERROR")
        db.collection(COLLECTION).document(job_id).update(
            {"status": "failed", "error": str(e), "updated_at": firestore.SERVER_TIMESTAMP}
        )
        return

    _log(f"JOB {job_id} ▶ Start  ({audio_uri})")

    tmp_dir = TMP_ROOT / f"job_{job_id}_{int(time.time())}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    storage_client = storage.Client()

    try:
        # ── 1. ダウンロード ───────────────────────
        local_audio = tmp_dir / Path(audio_uri).name
        bucket_name, blob_path = audio_uri[5:].split("/", 1)
        storage_client.bucket(bucket_name).blob(blob_path).download_to_filename(
            local_audio
        )
        _log(f"JOB {job_id}  ⤵  Downloaded → {local_audio}")

        # ── 2. フォーマット変換 (16 kHz / mono / wav) ─
        wav_path = tmp_dir / "audio_16k_mono.wav"
        convert_audio(str(local_audio), str(wav_path), use_gpu=USE_GPU)
        _log(f"JOB {job_id}  🎧 Converted → {wav_path}")

        # ── 3. 文字起こし ───────────────────────
        transcription_json = tmp_dir / "transcript.json"
        transcribe_audio(str(wav_path), str(transcription_json), device=DEVICE)
        _log(f"JOB {job_id}  ✍  Transcribed → {transcription_json}")

        # ── 4. 話者ダイアリゼーション ─────────────
        diarization_json = tmp_dir / "speaker.json"
        diarize_audio(
            str(wav_path),
            str(diarization_json),
            hf_auth_token=HF_AUTH_TOKEN,
            num_speakers=job.get("num_speakers"),
            min_speakers=job.get("min_speakers"),
            max_speakers=job.get("max_speakers"),
            device=DEVICE,
        )
        _log(f"JOB {job_id}  👥 Diarized → {diarization_json}")

        # ── 5. 結合 ────────────────────────────
        final_json = tmp_dir / "final.json"
        combine_results(str(transcription_json), str(diarization_json), str(final_json))
        _log(f"JOB {job_id}  🔗 Combined → {final_json}")

        # ── 6. アップロード ─────────────────────
        result_blob_path = f"whisper_results/{job_id}.json"
        storage_client.bucket(GCS_BUCKET_NAME).blob(result_blob_path).upload_from_filename(
            final_json
        )
        result_uri = f"gs://{GCS_BUCKET_NAME}/{result_blob_path}"
        _log(f"JOB {job_id}  ⬆  Uploaded → {result_uri}")

        # ── 7. Firestore 更新 ───────────────────
        db.collection(COLLECTION).document(job_id).update(
            {
                "status": "completed",
                "result_json_uri": result_uri,
                "completed_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
        )
        _log(f"JOB {job_id} ✔ Completed")

    except Exception as e:
        _log(f"JOB {job_id} ✖ Failed: {e}\n{traceback.format_exc()}", level="ERROR")
        db.collection(COLLECTION).document(job_id).update(
            {
                "status": "failed",
                "error": str(e),
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── メインループ ─────────────────────────────────
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
