import argparse
import os
import subprocess
import time
import datetime
import json
from typing import List, Optional, Dict, Any

import torch
from dotenv import load_dotenv
from google.cloud import pubsub_v1

from common_utils.logger import logger
from common_utils.class_types import WhisperPubSubMessageData

# ---------------------------------------------------------------------------
# 0. 事前設定（.env 読み込み）
# ---------------------------------------------------------------------------
CONFIG_PATH = "config/.env"
CONFIG_DEVELOP_PATH = "config_develop/.env.develop"

load_dotenv(CONFIG_PATH)
if os.path.exists(CONFIG_DEVELOP_PATH):
    load_dotenv(CONFIG_DEVELOP_PATH)


# ---------------------------------------------------------------------------
# 1. 共通ユーティリティ
# ---------------------------------------------------------------------------
def is_gcs_path(path: str) -> bool:
    """指定パスが GCS（gs://～）か判定"""
    return path.startswith("gs://")


def get_local_path(gcs_path: str) -> str:
    """GCS パスをローカル一時ファイル名に変換"""
    if not is_gcs_path(gcs_path):
        return gcs_path
    path_without_prefix = gcs_path[5:]  # remove "gs://"
    bucket_name, *_, filename = path_without_prefix.split("/")
    return f"/tmp/temp_{bucket_name}_{filename}"


def check_gpu_availability() -> None:
    """GPU が使えるかどうかを確認"""
    if not torch.cuda.is_available():
        raise RuntimeError(
            "GPU 環境が検出されませんでした。このスクリプトは GPU 上で動作する想定です。"
        )
    gpu_name = torch.cuda.get_device_name(0)
    gpu_count = torch.cuda.device_count()
    logger.info(f"GPU: {gpu_name} (total {gpu_count}) を検出しました")


def send_completion_notification(
    job_id: str,
    success: bool,
    error_message: Optional[str] = None,
) -> bool:
    """処理結果を Pub/Sub 経由で通知（WhisperPubSubMessageData 型に準拠）"""
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        pubsub_topic = os.environ.get("PUBSUB_TOPIC")
        if not (project_id and pubsub_topic):
            logger.warning("GCP_PROJECT_ID または PUBSUB_TOPIC が未設定のため通知をスキップします")
            return False

        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, pubsub_topic)

        msg = WhisperPubSubMessageData(
            job_id=job_id,
            event_type="job_completed" if success else "job_failed",
            error_message=error_message,
            timestamp=datetime.datetime.now().isoformat(),
        )

        future = publisher.publish(topic_path, data=json.dumps(msg.model_dump()).encode())
        message_id = future.result()
        logger.info("通知を送信しました (message_id=%s)", message_id)
        return True

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("通知送信エラー: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 2. メイン処理
# ---------------------------------------------------------------------------
def main() -> None:
    # ---- 2-1. 環境変数読み込み ------------------------------------------
    job_id = os.environ["JOB_ID"]
    full_audio_path = os.environ["FULL_AUDIO_PATH"]  # GCS or local
    full_transcription_path = os.environ["FULL_TRANSCRIPTION_PATH"]  # 出力先 GCS
    hf_auth_token = os.environ["HF_AUTH_TOKEN"]

    # Optional
    language = os.environ.get("LANGUAGE", "ja")
    initial_prompt = os.environ.get("INITIAL_PROMPT", "")
    device = os.environ.get("DEVICE", "cuda").lower()

    num_speakers = os.environ.get("NUM_SPEAKERS", "")
    min_speakers = os.environ.get("MIN_SPEAKERS", "1")
    max_speakers = os.environ.get("MAX_SPEAKERS", "1")

    # ---- 2-2. デバイス確認 ----------------------------------------------
    if device not in ("cpu", "cuda"):
        logger.warning("DEVICE=%s は無効です。cuda を使用します", device)
        device = "cuda"
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA が利用できません。cpu にフォールバックします")
        device = "cpu"
    if device == "cuda":
        check_gpu_availability()

    # ---- 2-3. 必須値チェック --------------------------------------------
    for name, val in [
        ("JOB_ID", job_id),
        ("FULL_AUDIO_PATH", full_audio_path),
        ("FULL_TRANSCRIPTION_PATH", full_transcription_path),
        ("HF_AUTH_TOKEN", hf_auth_token),
    ]:
        if not val:
            raise ValueError(f"環境変数 {name} が設定されていません")

    # ---- 2-4. 一時ファイルパス作成 (/tmp を利用し tmpfs に任せる) -------
    temp_dir = "/tmp"
    temp_wav_path = os.path.join(temp_dir, f"{job_id}.wav")
    transcription_json = os.path.join(temp_dir, f"{job_id}_transcription.json")
    diarization_json = os.path.join(temp_dir, f"{job_id}_diarization.json")

    total_start = time.time()
    logger.info("[%s] バッチ処理開始", job_id)

    try:
        # 1) 音声変換
        t0 = time.time()
        subprocess.run(
            [
                "python3",
                "convert_audio.py",
                full_audio_path,
                temp_wav_path,
                "--device",
                device,
            ],
            check=True,
        )
        logger.info("Step-1 convert_audio  : %.2fs", time.time() - t0)

        # 2) 文字起こし
        t0 = time.time()
        transcribe_cmd: List[str] = [
            "python3",
            "transcribe.py",
            temp_wav_path,
            transcription_json,
            "--device",
            device,
            "--language",
            language,
        ]
        if initial_prompt.strip():
            transcribe_cmd += ["--initial-prompt", initial_prompt]

        subprocess.run(transcribe_cmd, check=True)
        logger.info("Step-2 transcribe     : %.2fs", time.time() - t0)

        # 3) ダイアリゼーション
        t0 = time.time()
        diarize_cmd: List[str] = [
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
            diarize_cmd += ["--min-speakers", min_speakers, "--max-speakers", max_speakers]

        subprocess.run(diarize_cmd, check=True)
        logger.info("Step-3 diarize        : %.2fs", time.time() - t0)

        # 4) 結合して GCS へアップロード
        t0 = time.time()
        subprocess.run(
            [
                "python3",
                "combine_results.py",
                transcription_json,
                diarization_json,
                full_transcription_path,
            ],
            check=True,
        )
        logger.info("Step-4 combine_results: %.2fs", time.time() - t0)

        elapsed = time.time() - total_start
        logger.info("[%s] 正常終了 (%.2fs) => %s", job_id, elapsed, full_transcription_path)
        send_completion_notification(job_id, success=True)

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("[%s] 失敗: %s", job_id, exc)
        send_completion_notification(job_id, success=False, error_message=str(exc))
        raise

    finally:
        # /tmp は tmpfs だが、容量圧迫を防ぐため念のため削除
        for fp in (temp_wav_path, transcription_json, diarization_json):
            try:
                if os.path.exists(fp):
                    os.remove(fp)
                    logger.debug("一時ファイル削除: %s", fp)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("一時ファイル削除失敗 (%s): %s", fp, e)


# ---------------------------------------------------------------------------
# 3. CLI エントリポイント
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="音声文字起こし・話者分離バッチ")
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda"],
        default="cuda",
        help="使用デバイス (cpu / cuda)",
    )
    args = parser.parse_args()
    os.environ["DEVICE"] = args.device
    main()
