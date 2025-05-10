from __future__ import annotations

import datetime
import os
import shutil
import sys
import time
import traceback
import io
import pandas as pd
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google.cloud import firestore, storage
from common_utils.class_types import WhisperFirestoreData
from common_utils.logger import logger

# ── 外部ユーティリティ ─────────────────────────────
# 音声ファイル形式変換、文字起こし、話者分離、結果結合のためのモジュール
from whisper_batch.app.convert_audio import (
    convert_audio,
    check_audio_format,
)  # 音声ファイルを16kHzモノラルWAV形式に変換
from whisper_batch.app.transcribe import transcribe_audio  # 音声を文字起こし
from whisper_batch.app.diarize import diarize_audio  # 話者分離を実行
from whisper_batch.app.combine_results import (
    combine_results,
    read_json,
    save_dataframe,
)  # 文字起こしと話者分離の結果を結合

# ── .env 読み込み ────────────────────────────────
# 設定ファイルを読み込み、既存の環境変数を上書き

# スクリプトの場所を基準にする
BASE_DIR = Path(__file__).resolve().parent.parent
config_path = os.path.join(BASE_DIR, "config", ".env")
load_dotenv(config_path)

develop_config_path = os.path.join(BASE_DIR, "config_develop", ".env.develop")
if os.path.exists(develop_config_path):
    load_dotenv(develop_config_path)

# スクリプトの場所を基準にして、BASEDIRをつくって、GOOGLE_APPLICATION_CREDENTIALSについても絶対パスにする。
if str(BASE_DIR) not in os.environ["GOOGLE_APPLICATION_CREDENTIALS"]:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
        BASE_DIR, os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    )

# ── 環境変数（未設定時は KeyError を発生させる） ───────────────────────────────────
# COLLECTION 環境変数は必須。未設定なら起動時例外
try:
    COLLECTION = os.environ['COLLECTION']
except KeyError:
    raise RuntimeError(
        'Environment variable COLLECTION is required for whisper_batch'
    )
PROCESS_TIMEOUT_SECONDS: int = int(
    os.environ["PROCESS_TIMEOUT_SECONDS"]
)  # 処理タイムアウト時間（秒）
DURATION_TIMEOUT_FACTOR: float = float(
    os.environ["AUDIO_TIMEOUT_MULTIPLIER"]
)  # 音声長に基づくタイムアウト係数
POLL_INTERVAL_SECONDS: int = int(
    os.environ["POLL_INTERVAL_SECONDS"]
)  # ジョブ確認間隔（秒）
HF_AUTH_TOKEN: str = os.environ["HF_AUTH_TOKEN"]  # Hugging Face APIトークン
DEVICE: str = os.environ["DEVICE"].lower()  # 処理デバイス（"cuda"または"cpu"）
USE_GPU: bool = DEVICE == "cuda"  # GPUを使用するかどうか
TMP_ROOT: Path = Path(os.environ["LOCAL_TMP_DIR"])  # 一時ファイル保存ディレクトリ

# ファイル名テンプレート
AUDIO_TEMPLATE = os.environ["WHISPER_AUDIO_BLOB"]
TRANS_TEMPLATE = os.environ["WHISPER_TRANSCRIPT_BLOB"]
DIAR_TEMPLATE = os.environ["WHISPER_DIARIZATION_BLOB"]
COMBINE_TEMPLATE = os.environ["WHISPER_COMBINE_BLOB"]


def _utcnow() -> datetime.datetime:
    """
    現在のUTC時刻を返す

    Returns:
        datetime.datetime: タイムゾーン情報（UTC）付きの現在時刻
    """
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _mark_timeout_jobs(db: firestore.Client) -> None:
    """
    処理中のジョブでタイムアウトしたものを失敗状態にマークする

    Args:
        db (firestore.Client): Firestoreクライアントインスタンス

    Note:
        - 処理開始時刻から一定時間（基本タイムアウト時間か音声長に比例した時間の長い方）経過したジョブを検出
        - バッチ処理で該当ジョブのステータスを「失敗」に更新
        - WhisperFirestoreDataモデルを使ってデータを検証
    """
    now = _utcnow()
    col = db.collection(COLLECTION)
    batch = db.batch()
    updated = False
    for snap in col.where("status", "==", "processing").stream():
        data = snap.to_dict()
        # ドキュメントIDをjob_idとして追加
        data["job_id"] = snap.id
        # WhisperFirestoreDataでデータ検証
        try:
            firestore_data = WhisperFirestoreData(**data)
            # 以降はValidationが通ったデータを使用
            started_at = firestore_data.process_started_at
            if not started_at:
                # process_started_atがNoneのジョブは異常状態とみなし、失敗としてマーク
                batch.update(
                    snap.reference,
                    {
                        "status": "failed",
                        "error_message": "process_started_at is None",
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                )
                updated = True
                logger.warning(f"JOB {snap.id} ✖ process_started_atがNoneのため失敗としてマーク")
                continue

            # FirestoreのTimestamp型を適切に処理
            from google.cloud.firestore_v1._helpers import Timestamp

            if isinstance(started_at, Timestamp):
                started_at = started_at.to_datetime().replace(
                    tzinfo=datetime.timezone.utc
                )
            elif started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=datetime.timezone.utc)
            duration_ms = firestore_data.audio_duration_ms or 0
            # タイムアウト時間計算
            timeout_sec = max(
                PROCESS_TIMEOUT_SECONDS,
                int(duration_ms / 1000 * DURATION_TIMEOUT_FACTOR),
            )
            if (now - started_at).total_seconds() > timeout_sec:
                batch.update(
                    snap.reference,
                    {
                        "status": "failed",
                        "error_message": "timeout",
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                )
                updated = True
        except Exception as e:
            # データ検証エラーのログ記録
            logger.error(f"データ検証エラー (job_id={snap.id}): {e}")
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
        - WhisperFirestoreDataモデルを使ってデータを検証
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
        # Firestore 上のステータスを更新
        tx.update(
            doc.reference,
            {
                "status": "processing",
                "process_started_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        # 戻り値用データの組み立て（更新後のステータスを反映）
        try:
            data = doc.to_dict()
            data["job_id"] = doc.id  # ドキュメントIDを job_id として追加
            # ここでステータスを processing に上書き
            data["status"] = "processing"
            # WhisperFirestoreDataでデータ検証
            firestore_data = WhisperFirestoreData(**data)
            # 検証が通ったデータを辞書に戻して返す
            return dict(firestore_data.model_dump())
        except Exception as e:
            # データ検証エラーのログ記録
            logger.error(f"データ検証エラー (job_id={doc.id}): {e}")
            return None

    return _txn(db.transaction())


def _process_job(db: firestore.Client, job: Dict[str, Any]) -> None:
    """
    ジョブを処理する（ダウンロード、変換、文字起こし、話者分離、アップロード）

    Args:
        db (firestore.Client): Firestoreクライアントインスタンス
        job (Dict[str, Any]): 処理対象のジョブデータ

    Note:
        - WhisperFirestoreDataモデルを使ってデータを検証
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
    # WhisperFirestoreDataでデータ検証を試みる
    try:
        # データモデルを通して検証
        firestore_data = WhisperFirestoreData(**job)

        # 検証が通ったデータを使用
        job_id = firestore_data.job_id
        filename = firestore_data.filename
        bucket = firestore_data.gcs_bucket_name
        file_hash = firestore_data.file_hash
    except Exception as e:
        # データ検証エラーのログ記録
        job_id = job.get("job_id", "<unknown>")
        msg = f"データモデル検証エラー: {e}"
        logger.error(f"JOB {job_id} ✖ {msg}")
        if job_id != "<unknown>":
            db.collection(COLLECTION).document(job_id).update(
                {
                    "status": "failed",
                    "error_message": msg,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )
        return

    # ファイル拡張子と GCS パスの組み立て - テンプレートを使用
    ext = Path(filename).suffix.lstrip(".").lower()
    audio_blob = AUDIO_TEMPLATE.format(file_hash=file_hash, ext=ext)
    transcript_blob = TRANS_TEMPLATE.format(file_hash=file_hash)
    diarization_blob = DIAR_TEMPLATE.format(file_hash=file_hash)
    combine_blob = COMBINE_TEMPLATE.format(file_hash=file_hash)
    audio_uri = f"gs://{bucket}/{audio_blob}"
    transcript_uri = f"gs://{bucket}/{transcript_blob}"
    diarization_uri = f"gs://{bucket}/{diarization_blob}"  # 話者分離結果用のURI
    combine_uri = f"gs://{bucket}/{combine_blob}"  # 結合結果用のURI

    logger.info(f"JOB {job_id} ▶ Start (audio: {audio_uri})")

    # 一時ディレクトリの作成（ジョブIDとタイムスタンプを含む一意の名前）
    tmp_dir = TMP_ROOT / f"job_{job_id}_{int(time.time())}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    storage_client = storage.Client()

    try:
        # Cloud Storageから音声ファイルをダウンロード
        local_audio = tmp_dir / audio_blob
        storage_client.bucket(bucket).blob(audio_blob).download_to_filename(local_audio)
        logger.info(f"JOB {job_id} ⤵ Downloaded → {local_audio}")

        # 音声ファイルを16kHzモノラルWAV形式に変換（または既に適切な形式ならコピー）
        wav_path = tmp_dir / f"{file_hash}_16k_mono.wav"

        # ファイルが既に16kHzモノラルWAVか確認
        is_optimized_format = check_audio_format(str(local_audio))

        if is_optimized_format:
            # 既に適切なフォーマットならコピーするだけ
            shutil.copy2(str(local_audio), str(wav_path))
            logger.info(f"JOB {job_id} 🎧 Format already 16kHz mono WAV → {wav_path}")
        else:
            # 変換が必要な場合は通常通り変換
            convert_audio(str(local_audio), str(wav_path), use_gpu=USE_GPU)
            logger.info(f"JOB {job_id} 🎧 Converted → {wav_path}")

        # Whisperモデルによる文字起こし
        transcript_local = tmp_dir / transcript_blob
        transcribe_audio(
            str(wav_path), str(transcript_local), device=DEVICE, job_id=job_id
        )
        logger.info(f"JOB {job_id} ✍ Transcribed → {transcript_local}")

        # 話者数をチェック（文字列型の可能性があるので整数に変換）
        # NUM_SPEAKERS の安全パース
        try:
            num_speakers = int(os.getenv('NUM_SPEAKERS')) \
                if os.getenv('NUM_SPEAKERS') else None
        except ValueError:
            num_speakers = None
        min_speakers = int(job.get("min_speakers", 1))
        max_speakers = int(job.get("max_speakers", 1))

        # 話者分離またはシンプルな話者情報の生成
        diarization_local = tmp_dir / "speaker.json"

        # 単一話者かどうかを確認
        is_single_speaker = num_speakers == 1 or (
            num_speakers is None and max_speakers == 1
        )

        if is_single_speaker:
            # 単一話者の場合、話者分離をスキップして簡易的な話者情報を生成
            create_single_speaker_json(str(transcript_local), str(diarization_local))
            logger.info(f"JOB {job_id} 👤 Single speaker mode → {diarization_local}")
        else:
            # 複数話者の場合は通常通り話者分離を実行
            diarize_audio(
                str(wav_path),
                str(diarization_local),
                hf_auth_token=HF_AUTH_TOKEN,  # Hugging Face認証トークン
                num_speakers=num_speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                device=DEVICE,
                job_id=job_id,
            )
            logger.info(f"JOB {job_id} 👥 Diarized → {diarization_local}")

        # 文字起こしと話者分離の結果を結合（シンプルな話者情報の場合も同様）
        combine_local = tmp_dir / "combine.json"
        combine_results(str(transcript_local), str(diarization_local), str(combine_local))
        logger.info(f"JOB {job_id} 🔗 Combined → {combine_local}")

        # 文字起こし結果をCloud Storageにアップロード
        storage_client.bucket(bucket).blob(transcript_blob).upload_from_filename(
            transcript_local
        )
        logger.info(f"JOB {job_id} ⬆ Uploaded transcription → {transcript_uri}")

        # 話者分離結果をCloud Storageにアップロード
        storage_client.bucket(bucket).blob(diarization_blob).upload_from_filename(diarization_local)
        logger.info(f"JOB {job_id} ⬆ Uploaded diarization result → {diarization_uri}")

        # 結合結果を別ファイルとしてCloud Storageにアップロード
        storage_client.bucket(bucket).blob(combine_blob).upload_from_filename(combine_local)
        logger.info(f"JOB {job_id} ⬆ Uploaded combine result → {combine_uri}")

        # 処理成功をFirestoreに反映する前に現在のステータスを確認
        job_doc = db.collection(COLLECTION).document(job_id).get()
        if not job_doc.exists:
            logger.error(
                f"JOB {job_id} ✖ ドキュメントが見つかりません。更新をスキップします。"
            )
        else:
            current_status = job_doc.to_dict().get("status", "")
            if current_status != "processing":
                logger.error(
                    f"JOB {job_id} ✖ 現在のステータスが processing ではありません（{current_status}）。更新をスキップします。"
                )
            else:
                # ステータスが"processing"の場合のみ更新
                db.collection(COLLECTION).document(job_id).update(
                    {
                        "status": "completed",
                        "process_ended_at": firestore.SERVER_TIMESTAMP,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    }
                )
                logger.info(f"JOB {job_id} ✔ Completed")

    except Exception as e:
        # エラー発生時の処理
        err = str(e)
        logger.error(f"JOB {job_id} ✖ Failed: {err}\n{traceback.format_exc()}")

        # Firestoreのドキュメントを取得
        job_doc = db.collection(COLLECTION).document(job_id).get()

        if not job_doc.exists:
            logger.error(
                f"JOB {job_id} ✖ エラー発生時にドキュメントが見つかりません。更新をスキップします。"
            )
        else:
            job_data = job_doc.to_dict() or {}
            current_status = job_data.get("status", "")

            if current_status != "processing":
                logger.error(
                    f"JOB {job_id} ✖ エラー発生時に現在のステータスが processing ではありません（{current_status}）。更新をスキップします。"
                )
            else:
                # ステータスが"processing"の場合のみ更新
                # 更新データを準備
                update_data = {
                    "status": "failed",
                    "error_message": err,
                    "process_ended_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }

                # process_started_atがない場合は追加（タイムアウト判定のため）
                if not job_data.get("process_started_at"):
                    update_data["process_started_at"] = firestore.SERVER_TIMESTAMP

                # 更新を実行
                db.collection(COLLECTION).document(job_id).update(update_data)
                logger.error(f"JOB {job_id} ✖ 処理失敗を記録しました: {err}")

    finally:
        # 一時ファイルの削除（エラーが発生しても削除を試みる）
        shutil.rmtree(tmp_dir, ignore_errors=True)


def create_single_speaker_json(transcription_path, output_path):
    """
    単一話者用の話者情報JSONを生成する

    Args:
        transcription_path (str): 文字起こし結果JSONのパス
        output_path (str): 出力する話者情報JSONのパス
    """
    try:
        # 文字起こし結果を読み込む
        transcription_df = read_json(transcription_path)

        # 単一話者用のデータを作成
        speaker_data = []
        for _, row in transcription_df.iterrows():
            speaker_data.append(
                {
                    "start": row["start"],
                    "end": row["end"],
                    "speaker": "SPEAKER_01",  # 全セグメントを同一話者に割り当て
                }
            )

        # データフレームに変換して保存
        speaker_df = pd.DataFrame(speaker_data)
        save_dataframe(speaker_df, output_path)

        logger.info(f"単一話者JSONを生成しました: {output_path}")

    except Exception as e:
        # エラー時は最小限の話者情報を生成（空のJSON配列）
        logger.error(f"単一話者JSONの生成中にエラー: {e}")

        if output_path.startswith("gs://"):
            # GCSの場合
            path_without_prefix = output_path[5:]
            bucket_name, blob_path = path_without_prefix.split("/", 1)

            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_path)

            blob.upload_from_string("[]", content_type="application/json")
        else:
            # ローカルの場合
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w") as f:
                json.dump([], f)


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
                logger.info("キューが空です。待機…")
                time.sleep(POLL_INTERVAL_SECONDS)  # 一定時間待機
        except KeyboardInterrupt:
            logger.info("SIGINT 受信。ワーカーを終了します")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}\n{traceback.format_exc()}")
            time.sleep(POLL_INTERVAL_SECONDS)  # エラー時も一定時間待機


def run_batch_job():
    """
    バッチジョブとして実行する処理を集約した関数
    
    Returns:
        bool: 処理が成功したかどうか
    """
    # GCPのバッチジョブとして実行された場合はJOB_IDを環境変数から取得
    job_id = os.environ.get("JOB_ID")
    if not job_id:
        logger.error("JOB_ID 環境変数が設定されていません")
        return False
        
    db = firestore.Client()
    
    # ステータスを"processing"に更新
    doc_ref = db.collection(COLLECTION).document(job_id)
    try:
        doc_ref.update({
            "status": "processing",
            "process_started_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        logger.info(f"JOB {job_id} ▶ Status updated to 'processing'")
    except Exception as e:
        logger.error(f"JOB {job_id} ✖ Failed to update status: {str(e)}")
        return False
    
    # Firestoreからジョブデータを取得
    job_doc = doc_ref.get()
    if not job_doc.exists:
        logger.error(f"JOB {job_id} ✖ Job document not found in Firestore")
        return False
        
    job_data = job_doc.to_dict()
    job_data["job_id"] = job_id  # job_idをデータに追加
    try:
        # ジョブを処理
        _process_job(db, job_data)
        return True
    except Exception as e:
        # 例外時はステータスを"failed"に更新
        error_message = f"Exception in batch job: {str(e)}\n{traceback.format_exc()}"
        logger.error(f"JOB {job_id} ✖ {error_message}")
        doc_ref.update({
            "status": "failed",
            "error_message": str(e),
            "process_ended_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        return False

if __name__ == "__main__":
    # バッチジョブかワーカーモードかを判断
    if os.environ.get("JOB_ID"):
        # バッチジョブとして実行
        try:
            success = run_batch_job()
            if not success:
                sys.exit(1)  # 処理失敗時は非ゼロで終了
        except Exception as e:
            logger.critical(f"Fatal error in batch job: {str(e)}", exc_info=True)
            sys.exit(1)  # 例外発生時も非ゼロで終了
    else:
        # ワーカーモードとして実行
        main()
