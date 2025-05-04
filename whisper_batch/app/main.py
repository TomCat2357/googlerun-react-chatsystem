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
# 音声ファイル形式変換、文字起こし、話者分離、結果結合のためのモジュール
from convert_audio import convert_audio  # 音声ファイルを16kHzモノラルWAV形式に変換
from transcribe import transcribe_audio  # 音声を文字起こし
from diarize import diarize_audio        # 話者分離を実行
from combine_results import combine_results  # 文字起こしと話者分離の結果を結合

# ── .env 読み込み ────────────────────────────────
# 設定ファイルを読み込み、既存の環境変数を上書き
load_dotenv("config/.env", override=True)

# ── 環境変数（未設定時は KeyError を発生させる） ───────────────────────────────────
COLLECTION: str = os.environ["WHISPER_JOBS_COLLECTION"]  # Firestoreのコレクション名
PROCESS_TIMEOUT_SECONDS: int = int(os.environ["PROCESS_TIMEOUT_SECONDS"])  # 処理タイムアウト時間（秒）
DURATION_TIMEOUT_FACTOR: float = float(os.environ["AUDIO_TIMEOUT_MULTIPLIER"])  # 音声長に基づくタイムアウト係数
POLL_INTERVAL_SECONDS: int = int(os.environ["POLL_INTERVAL_SECONDS"])  # ジョブ確認間隔（秒）
HF_AUTH_TOKEN: str = os.environ["HF_AUTH_TOKEN"]  # Hugging Face APIトークン
DEVICE: str = os.environ["DEVICE"].lower()  # 処理デバイス（"cuda"または"cpu"）
USE_GPU: bool = DEVICE == "cuda"  # GPUを使用するかどうか
TMP_ROOT: Path = Path(os.environ["LOCAL_TMP_DIR"])  # 一時ファイル保存ディレクトリ


def _utcnow() -> datetime.datetime:
    """
    現在のUTC時刻を返す
    
    Returns:
        datetime.datetime: タイムゾーン情報（UTC）付きの現在時刻
    """
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _log(msg: str, level: str = "INFO") -> None:
    """
    タイムスタンプ付きでログメッセージを出力する
    
    Args:
        msg (str): 出力するメッセージ本文
        level (str, optional): ログレベル（"INFO"または"ERROR"など）。デフォルトは"INFO"
    
    Note:
        ERRORレベルの場合は標準エラー出力に、それ以外は標準出力に出力する
    """
    ts = _utcnow().isoformat(timespec="seconds")
    out = sys.stderr if level.upper() == "ERROR" else sys.stdout
    print(f"{ts} [{level}] {msg}", file=out, flush=True)


def _mark_timeout_jobs(db: firestore.Client) -> None:
    """
    処理中のジョブでタイムアウトしたものを失敗状態にマークする
    
    Args:
        db (firestore.Client): Firestoreクライアントインスタンス
    
    Note:
        - 処理開始時刻から一定時間（基本タイムアウト時間か音声長に比例した時間の長い方）経過したジョブを検出
        - バッチ処理で該当ジョブのステータスを「失敗」に更新
    """
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
        # タイムアウト時間は基本タイムアウト時間か音声長に比例した時間の長い方を採用
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
    """
    キューから次の処理対象ジョブを取得してステータスを「処理中」に更新する
    
    Args:
        db (firestore.Client): Firestoreクライアントインスタンス
    
    Returns:
        Optional[Dict[str, Any]]: ジョブデータ（キューが空の場合はNone）
    
    Note:
        - トランザクション内で処理を実行してジョブの競合を防止
        - 作成日時の古い順に1件取得し、ステータスを「processing」に更新
        - ドキュメントIDを「job_id」キーに追加してジョブデータを返す
    """
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
    """
    ジョブを処理する（ダウンロード、変換、文字起こし、話者分離、アップロード）
    
    Args:
        db (firestore.Client): Firestoreクライアントインスタンス
        job (Dict[str, Any]): 処理対象のジョブデータ
    
    Note:
        - 必須メタデータ（job_id, filename, gcs_bucket_name, file_hash）の検証
        - Cloud Storageから音声ファイルをダウンロード
        - 音声ファイルを16kHzモノラルWAV形式に変換
        - Whisperモデルによる文字起こし
        - 話者分離の実行
        - 文字起こしと話者分離の結果を結合
        - 結合結果をCloud Storageにアップロード
        - 処理結果をFirestoreに反映
        - エラー発生時は例外をキャッチしてエラー情報を記録
        - 一時ファイルは処理完了後に削除
    """
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

    # 一時ディレクトリの作成（ジョブIDとタイムスタンプを含む一意の名前）
    tmp_dir = TMP_ROOT / f"job_{job_id}_{int(time.time())}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    storage_client = storage.Client()

    try:
        # Cloud Storageから音声ファイルをダウンロード
        local_audio = tmp_dir / audio_blob
        storage_client.bucket(bucket).blob(audio_blob).download_to_filename(local_audio)
        _log(f"JOB {job_id} ⤵ Downloaded → {local_audio}")

        # 音声ファイルを16kHzモノラルWAV形式に変換
        wav_path = tmp_dir / f"{file_hash}_16k_mono.wav"
        convert_audio(str(local_audio), str(wav_path), use_gpu=USE_GPU)
        _log(f"JOB {job_id} 🎧 Converted → {wav_path}")

        # Whisperモデルによる文字起こし
        transcript_local = tmp_dir / transcript_blob
        transcribe_audio(str(wav_path), str(transcript_local), device=DEVICE)
        _log(f"JOB {job_id} ✍ Transcribed → {transcript_local}")

        # 話者分離の実行
        diarization_local = tmp_dir / "speaker.json"
        diarize_audio(
            str(wav_path),
            str(diarization_local),
            hf_auth_token=HF_AUTH_TOKEN,  # Hugging Face認証トークン
            num_speakers=job.get("num_speakers"),  # 話者数（指定がある場合）
            min_speakers=job.get("min_speakers", 1),  # 最小話者数（デフォルト1）
            max_speakers=job.get("max_speakers", 1),  # 最大話者数（デフォルト1）
            device=DEVICE,  # 使用デバイス（CUDA/CPU）
        )
        _log(f"JOB {job_id} 👥 Diarized → {diarization_local}")

        # 文字起こしと話者分離の結果を結合
        final_local = tmp_dir / "final.json"
        combine_results(str(transcript_local), str(diarization_local), str(final_local))
        _log(f"JOB {job_id} 🔗 Combined → {final_local}")

        # 結合結果をCloud Storageにアップロード
        storage_client.bucket(bucket).blob(transcript_blob).upload_from_filename(final_local)
        _log(f"JOB {job_id} ⬆ Uploaded → {transcript_uri}")

        # 処理成功をFirestoreに反映
        db.collection(COLLECTION).document(job_id).update({
            "status": "completed",
            "result_json_uri": transcript_uri,
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        _log(f"JOB {job_id} ✔ Completed")

    except Exception as e:
        # エラー発生時の処理
        err = str(e)
        _log(f"JOB {job_id} ✖ Failed: {err}\n{traceback.format_exc()}", level="ERROR")
        db.collection(COLLECTION).document(job_id).update({
            "status": "failed",
            "error_message": err,
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

    finally:
        # 一時ファイルの削除（エラーが発生しても削除を試みる）
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    """
    メインループ処理
    
    Note:
        - Firestoreクライアントを初期化
        - 無限ループで以下の処理を繰り返す：
          1. タイムアウトしたジョブをマーク
          2. 次のジョブを取得して処理
          3. ジョブがなければ一定時間待機
        - Ctrl+Cで終了可能
        - 予期せぬエラーは記録して待機後に再試行
    """
    db = firestore.Client()
    while True:
        try:
            _mark_timeout_jobs(db)  # タイムアウトジョブをマーク
            job = _pick_next_job(db)  # 次のジョブを取得
            if job:
                _process_job(db, job)  # ジョブを処理
            else:
                _log("キューが空です。待機…")
                time.sleep(POLL_INTERVAL_SECONDS)  # 一定時間待機
        except KeyboardInterrupt:
            _log("SIGINT 受信。ワーカーを終了します", level="INFO")
            break
        except Exception as e:
            _log(f"Main loop error: {e}\n{traceback.format_exc()}", level="ERROR")
            time.sleep(POLL_INTERVAL_SECONDS)  # エラー時も一定時間待機


if __name__ == "__main__":
    main()