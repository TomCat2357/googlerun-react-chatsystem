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
from whisper_batch.app.convert_audio import (
    convert_audio,
    check_audio_format,
)
from whisper_batch.app.transcribe import transcribe_audio
from whisper_batch.app.diarize import diarize_audio
from whisper_batch.app.combine_results import (
    combine_results,
    read_json,
    save_dataframe,
)

# ── .env 読み込み ────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
config_path = os.path.join(BASE_DIR, "config", ".env")
load_dotenv(config_path)

develop_config_path = os.path.join(BASE_DIR, "config_develop", ".env.develop")
if os.path.exists(develop_config_path):
    load_dotenv(develop_config_path)

if str(BASE_DIR) not in os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
        BASE_DIR, os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    )

# ── 環境変数（未設定時は KeyError を発生させる） ───────────────────────────────────
try:
    COLLECTION = os.environ['COLLECTION']
except KeyError:
    raise RuntimeError(
        'Environment variable COLLECTION is required for whisper_batch'
    )
# PROCESS_TIMEOUT_SECONDS と AUDIO_TIMEOUT_MULTIPLIER の読み込みは backend 側に移管するため削除
# PROCESS_TIMEOUT_SECONDS と AUDIO_TIMEOUT_MULTIPLIER の読み込みは backend 側に移管するため削除
POLL_INTERVAL_SECONDS: int = int(
    os.environ.get("POLL_INTERVAL_SECONDS", "10") # Default if not set
)
HF_AUTH_TOKEN: str = os.environ["HF_AUTH_TOKEN"]
DEVICE: str = os.environ["DEVICE"].lower()
USE_GPU: bool = DEVICE == "cuda"
TMP_ROOT: Path = Path(os.environ["LOCAL_TMP_DIR"])

AUDIO_TEMPLATE = os.environ["WHISPER_AUDIO_BLOB"]
TRANS_TEMPLATE = os.environ["WHISPER_TRANSCRIPT_BLOB"]
DIAR_TEMPLATE = os.environ["WHISPER_DIARIZATION_BLOB"]
COMBINE_TEMPLATE = os.environ["WHISPER_COMBINE_BLOB"]


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)

# _mark_timeout_jobs 関数を削除します

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
        try:
            data = doc.to_dict()
            data["job_id"] = doc.id
            data["status"] = "processing"
            firestore_data = WhisperFirestoreData(**data)
            return dict(firestore_data.model_dump())
        except Exception as e:
            logger.error(f"データ検証エラー (job_id={doc.id}): {e}")
            # トランザクション内でエラーを発生させてロールバックさせるか、
            # あるいはこのジョブをスキップ（failedにするなど）するか検討が必要
            # ここではNoneを返して処理をスキップする
            return None
    return _txn(db.transaction())


def _process_job(db: firestore.Client, job: Dict[str, Any]) -> None:
    # WhisperFirestoreDataでデータ検証を試みる
    try:
        firestore_data = WhisperFirestoreData(**job)
        job_id = firestore_data.job_id
        filename = firestore_data.filename
        bucket = firestore_data.gcs_bucket_name
        file_hash = firestore_data.file_hash
        # language, initial_prompt, num_speakers, min_speakers, max_speakers を取得
        language = firestore_data.language
        initial_prompt = firestore_data.initial_prompt
        num_speakers = firestore_data.num_speakers
        min_speakers = firestore_data.min_speakers
        max_speakers = firestore_data.max_speakers

    except Exception as e:
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

    ext = Path(filename).suffix.lstrip(".").lower()
    # audio_blobのファイル名に拡張子を含める
    original_audio_filename = os.environ["WHISPER_AUDIO_BLOB"].format(file_hash=file_hash, ext=ext)
    gcs_path_prefix = f"whisper/{firestore_data.user_id}/{file_hash}" # firestore_dataからuser_idを取得
    audio_blob = f"{gcs_path_prefix}/{original_audio_filename}"

    transcript_blob_filename = os.environ["WHISPER_TRANSCRIPT_BLOB"].format(file_hash=file_hash)
    transcript_blob = f"{gcs_path_prefix}/{transcript_blob_filename}"

    diarization_blob_filename = os.environ["WHISPER_DIARIZATION_BLOB"].format(file_hash=file_hash)
    diarization_blob = f"{gcs_path_prefix}/{diarization_blob_filename}"
    
    combine_blob_filename = os.environ["WHISPER_COMBINE_BLOB"].format(file_hash=file_hash)
    combine_blob = f"{gcs_path_prefix}/{combine_blob_filename}"


    audio_uri = f"gs://{bucket}/{audio_blob}"
    transcript_uri = f"gs://{bucket}/{transcript_blob}"
    diarization_uri = f"gs://{bucket}/{diarization_blob}"
    combine_uri = f"gs://{bucket}/{combine_blob}"

    logger.info(f"JOB {job_id} ▶ Start (audio: {audio_uri})")

    tmp_dir = TMP_ROOT / f"job_{job_id}_{int(time.time())}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    storage_client = storage.Client()

    try:
        # Download: firestore_data.audio_file_path を使う
        if not firestore_data.audio_file_path:
            raise ValueError("audio_file_path is not set in Firestore data")
        local_audio = tmp_dir / Path(firestore_data.audio_file_path).name # GCS上のファイル名をローカル名として使用

        storage_client.bucket(bucket).blob(firestore_data.audio_file_path).download_to_filename(local_audio)
        logger.info(f"JOB {job_id} ⤵ Downloaded → {local_audio} from gs://{bucket}/{firestore_data.audio_file_path}")

        wav_path = tmp_dir / f"{file_hash}_16k_mono.wav"
        is_optimized_format = check_audio_format(str(local_audio))
        if is_optimized_format:
            shutil.copy2(str(local_audio), str(wav_path))
            logger.info(f"JOB {job_id} 🎧 Format already 16kHz mono WAV → {wav_path}")
        else:
            convert_audio(str(local_audio), str(wav_path), use_gpu=USE_GPU)
            logger.info(f"JOB {job_id} 🎧 Converted → {wav_path}")

        # 文字起こし時に言語とプロンプトを渡す
        transcript_local_filename = Path(transcript_blob).name
        transcript_local = tmp_dir / transcript_local_filename
        transcribe_audio(
            str(wav_path), str(transcript_local),
            device=DEVICE, job_id=job_id,
            language=language, initial_prompt=initial_prompt
        )
        logger.info(f"JOB {job_id} ✍ Transcribed → {transcript_local}")

        diarization_local_filename = Path(diarization_blob).name
        diarization_local = tmp_dir / diarization_local_filename # GCSにアップロードするファイル名と合わせる

        is_single_speaker = num_speakers == 1 or (
            num_speakers is None and max_speakers == 1 and min_speakers == 1 # min_speakersも考慮
        )

        if is_single_speaker:
            create_single_speaker_json(str(transcript_local), str(diarization_local))
            logger.info(f"JOB {job_id} 👤 Single speaker mode → {diarization_local}")
        else:
            diarize_audio(
                str(wav_path),
                str(diarization_local),
                hf_auth_token=HF_AUTH_TOKEN,
                num_speakers=num_speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                device=DEVICE,
                job_id=job_id,
            )
            logger.info(f"JOB {job_id} 👥 Diarized → {diarization_local}")

        # 結合結果のローカルファイルパス
        combine_local_filename = Path(combine_blob).name
        combine_local = tmp_dir / combine_local_filename # GCSにアップロードするファイル名と合わせる
        
        # combine_results に渡すパスを修正
        combine_results(str(transcript_local), str(diarization_local), str(combine_local))
        logger.info(f"JOB {job_id} 🔗 Combined → {combine_local}")

        # Upload: firestore_data.transcription_file_path を使う
        if not firestore_data.transcription_file_path:
             raise ValueError("transcription_file_path is not set in Firestore data for combined results")
        storage_client.bucket(bucket).blob(firestore_data.transcription_file_path).upload_from_filename(
            combine_local
        )
        logger.info(f"JOB {job_id} ⬆ Uploaded combined result → gs://{bucket}/{firestore_data.transcription_file_path}")

        # 個別の文字起こし結果と話者分離結果もアップロード（必要であれば）
        # storage_client.bucket(bucket).blob(transcript_blob).upload_from_filename(
        #     transcript_local
        # )
        # logger.info(f"JOB {job_id} ⬆ Uploaded transcription → {transcript_uri}")
        # storage_client.bucket(bucket).blob(diarization_blob).upload_from_filename(diarization_local)
        # logger.info(f"JOB {job_id} ⬆ Uploaded diarization result → {diarization_uri}")


        job_doc = db.collection(COLLECTION).document(job_id).get()
        if not job_doc.exists:
            logger.error(
                f"JOB {job_id} ✖ ドキュメントが見つかりません。更新をスキップします。"
            )
        else:
            current_status = job_doc.to_dict().get("status", "")
            if current_status != "processing": # backend側でキャンセルされた場合などを考慮
                logger.warning(
                    f"JOB {job_id} Current status is '{current_status}', not 'processing'. Skipping 'completed' update from worker."
                )
            else:
                # 処理成功。Firestoreに文字起こし結果のセグメントも保存
                segments_data = []
                if os.path.exists(combine_local):
                    with open(combine_local, 'r', encoding='utf-8') as f:
                        combined_json_data = json.load(f)
                        if isinstance(combined_json_data, list): # ルートがリストであることを期待
                             segments_data = combined_json_data
                        elif isinstance(combined_json_data, dict) and "segments" in combined_json_data: # "segments"キーを持つ辞書の場合
                             segments_data = combined_json_data["segments"]

                db.collection(COLLECTION).document(job_id).update(
                    {
                        "status": "completed",
                        "segments": segments_data, # 結合された文字起こし結果のセグメントを保存
                        "process_ended_at": firestore.SERVER_TIMESTAMP,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                        "error_message": None # 成功時はエラーメッセージをクリア
                    }
                )
                logger.info(f"JOB {job_id} ✔ Completed and segments saved to Firestore.")

    except Exception as e:
        err = str(e)
        logger.error(f"JOB {job_id} ✖ Failed: {err}\n{traceback.format_exc()}")
        job_doc = db.collection(COLLECTION).document(job_id).get()
        if not job_doc.exists:
            logger.error(
                f"JOB {job_id} ✖ エラー発生時にドキュメントが見つかりません。更新をスキップします。"
            )
        else:
            # current_status = job_doc.to_dict().get("status", "") # backend側でキャンセルされた場合などを考慮
            # if current_status != "processing":
            #    logger.warning(f"JOB {job_id} Current status is '{current_status}', not 'processing'. Skipping 'failed' update from worker.")
            # else:
            db.collection(COLLECTION).document(job_id).update(
                {
                    "status": "failed",
                    "error_message": err,
                    "process_ended_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def create_single_speaker_json(transcription_path_str: str, output_path_str: str):
    transcription_path = Path(transcription_path_str)
    output_path = Path(output_path_str)
    try:
        transcription_df = read_json(transcription_path)
        speaker_data = []
        for _, row in transcription_df.iterrows():
            speaker_data.append(
                {
                    "start": row["start"],
                    "end": row["end"],
                    "speaker": "SPEAKER_01",
                }
            )
        speaker_df = pd.DataFrame(speaker_data)
        # output_pathの親ディレクトリが存在しない場合は作成
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_dataframe(speaker_df, output_path)
        logger.info(f"単一話者JSONを生成しました: {output_path}")
    except Exception as e:
        logger.error(f"単一話者JSONの生成中にエラー: {e}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump([], f)


def main_loop() -> None:
    db = firestore.Client()
    logger.info("ワーカーモードで起動しました。ジョブキューをポーリングします...")
    while True:
        try:
            job = _pick_next_job(db)
            if job:
                _process_job(db, job)
            else:
                # logger.info("キューが空です。待機…") # ログ出力を抑制する場合
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("SIGINT 受信。ワーカーを終了します")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}\n{traceback.format_exc()}")
            time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    # 常にワーカーモード (main_loop) を実行
    main_loop()
