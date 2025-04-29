import argparse
import os
import subprocess
import time
import torch
from google.cloud import pubsub_v1
import json
import datetime
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from common_utils.logger import logger
from common_utils.class_types import WhisperPubSubMessageData

# 環境変数ファイルが存在する場合のみ読み込む
config_path: str = "config/.env"
config_develop_path: str = "config_develop/.env.develop"

load_dotenv(config_path)

if os.path.exists(config_develop_path):
    load_dotenv(config_develop_path)


def is_gcs_path(path: str) -> bool:
    """GCSパスかどうかを判定する"""
    return path.startswith("gs://")


def get_local_path(gcs_path: str) -> str:
    """GCSパスからローカル一時ファイルパスを生成する"""
    if not is_gcs_path(gcs_path):
        return gcs_path

    path_without_prefix: str = gcs_path[5:]
    parts: List[str] = path_without_prefix.split("/")
    bucket_name: str = parts[0]
    file_name: str = parts[-1]
    return f"temp_{bucket_name}_{file_name}"


def check_gpu_availability() -> None:
    """GPUが利用可能かどうかを確認する"""
    if not torch.cuda.is_available():
        raise Exception(
            "GPU環境が検出されませんでした。このスクリプトはGPU環境でのみ実行できます。"
        )

    gpu_name: str = torch.cuda.get_device_name(0)
    gpu_count: int = torch.cuda.device_count()
    logger.info(f"GPUが検出されました: {gpu_name} (合計{gpu_count}台)")


def send_completion_notification(
    job_id: str,
    success: bool,
    error_message: Optional[str] = None,
) -> bool:
    """処理完了通知をPub/Subに送信する（型定義に合わない情報は送らない）"""
    try:
        project_id: str = os.environ.get("GCP_PROJECT_ID")
        pubsub_topic: str = os.environ.get("PUBSUB_TOPIC")
        if not pubsub_topic or not project_id:
            logger.warning(
                "PROJECT_IDまたはPUBSUB_TOPICが設定されていないため、通知を送信できません"
            )
            return False

        publisher: pubsub_v1.PublisherClient = pubsub_v1.PublisherClient()
        topic_path: str = publisher.topic_path(project_id, pubsub_topic)

        # WhisperPubSubMessageData 型に strictly 準拠
        message_data: WhisperPubSubMessageData = WhisperPubSubMessageData(
            job_id=job_id,
            event_type="job_completed" if success else "job_failed",
            error_message=error_message,
            timestamp=datetime.datetime.now().isoformat(),
        )

        message_dict: Dict[str, Any] = message_data.model_dump()

        message_bytes: bytes = json.dumps(message_dict).encode("utf-8")
        future = publisher.publish(topic_path, data=message_bytes)
        message_id: str = future.result()

        logger.info("処理完了通知を送信しました: %s", message_id)
        return True

    except Exception as e:
        logger.error("処理完了通知の送信エラー: %s", str(e))
        return False



def main() -> None:
    # ---- 0. 環境変数 ------------------------------------------------------
    job_id = os.environ["JOB_ID"]
    audio_path = os.environ["AUDIO_PATH"]  # GCS or local
    transcription_path = os.environ["TRANSCRIPTION_PATH"]  # GCS への最終出力
    hf_auth_token = os.environ["HF_AUTH_TOKEN"]

    # 話者数関連
    num_speakers = os.environ.get("NUM_SPEAKERS", "")
    min_speakers = os.environ.get("MIN_SPEAKERS", "1")  # ← ★① 修正
    max_speakers = os.environ.get("MAX_SPEAKERS", "1")

    # Whisper の追加設定
    language = os.environ.get("LANGUAGE", "ja")
    initial_prompt = os.environ.get("INITIAL_PROMPT", "")

    # デバイス決定
    device = os.environ.get("DEVICE", "cuda").lower()
    if device not in ("cpu", "cuda"):
        logger.warning(f"無効なデバイス指定: {device} → 'cuda' を使用")
        device = "cuda"
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA が無いので CPU にフォールバック")
        device = "cpu"
    if device == "cuda":
        check_gpu_availability()

    # ---- 1. 必須値のバリデーション ---------------------------------------
    for name, value in [
        ("JOB_ID", job_id),
        ("AUDIO_PATH", audio_path),
        ("HF_AUTH_TOKEN", hf_auth_token),
        ("TRANSCRIPTION_PATH", transcription_path),
    ]:
        if not value:
            raise ValueError(f"環境変数 {name} が設定されていません")

    # ---- 2. 一時ファイル名の準備 ----------------------------------------
    temp_wav_path = f"temp_{job_id}.wav"
    transcription_json = f"temp_{job_id}_transcription.json"
    diarization_json = f"temp_{job_id}_diarization.json"
    output_gcs_path = transcription_path  # ← ★③ 修正

    total_start = time.time()
    logger.info(f"[{job_id}] バッチ処理を開始")

    try:
        # 2-1 音声を 16 kHz/mono WAV へ変換 -------------------------------
        step1_start = time.time()
        subprocess.run(
            [
                "python3",
                "convert_audio.py",
                audio_path,
                temp_wav_path,
                "--device",
                device,
            ],
            check=True,
        )
        logger.info(f"Step-1 Audio convert: {time.time() - step1_start:.2f}s")

        # 2-2 文字起こし --------------------------------------------------
        step2_start = time.time()
        subprocess.run(
            [
                "python3",
                "transcribe.py",
                temp_wav_path,
                transcription_json,
                "--device",
                device,
            ],
            check=True,
        )
        logger.info(f"Step-2 Transcribe  : {time.time() - step2_start:.2f}s")

        # 2-3 話者ダイアリゼーション ------------------------------------
        step3_start = time.time()
        diarize_cmd = [
            "python3",
            "diarize.py",
            temp_wav_path,
            diarization_json,
            hf_auth_token,
            "--device",
            device,
        ]
        if num_speakers.strip():
            diarize_cmd += ["--num-speakers", num_speakers]
        else:
            diarize_cmd += [
                "--min-speakers",
                min_speakers,
                "--max-speakers",
                max_speakers,
            ]
        subprocess.run(diarize_cmd, check=True)
        logger.info(f"Step-3 Diarization : {time.time() - step3_start:.2f}s")

        # 2-4 文字起こし＋話者情報を結合し GCS へ書き込み ----------------
        step4_start = time.time()
        subprocess.run(
            [
                "python3",
                "combine_results.py",
                transcription_json,
                diarization_json,
                output_gcs_path,
            ],
            check=True,
        )
        logger.info(f"Step-4 Combine     : {time.time() - step4_start:.2f}s")

        total_time = time.time() - total_start
        logger.info(f"[{job_id}] 処理完了 ({total_time:.2f}s) → {output_gcs_path}")

        send_completion_notification(
            job_id, True, processing_time=total_time, result_path=output_gcs_path
        )

    except Exception as err:
        logger.error(f"[{job_id}] エラー: {err}")
        send_completion_notification(job_id, False, error_message=str(err))
        raise

    finally:
        for fp in (temp_wav_path, transcription_json, diarization_json):
            try:
                if os.path.exists(fp):
                    os.remove(fp)
                    logger.debug(f"削除: {fp}")
            except Exception as e:
                logger.warning(f"一時ファイル削除失敗 {fp}: {e}")


if __name__ == "__main__":
    # CLIでも呼び出せるように引数解析を追加
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="音声文字起こしと話者分離のバッチ処理"
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda"],
        default="cuda",
        help="使用するデバイス (CPU または CUDA GPU)",
    )
    args: argparse.Namespace = parser.parse_args()

    # 環境変数にデバイス情報を設定
    os.environ["DEVICE"] = args.device

    main()
