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
from common_utils.class_types import JobMessageData

# 環境変数ファイルが存在する場合のみ読み込む
config_path: str = 'config/.env'
config_develop_path: str = 'config_develop/.env.develop'

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
        raise Exception("GPU環境が検出されませんでした。このスクリプトはGPU環境でのみ実行できます。")
    
    gpu_name: str = torch.cuda.get_device_name(0)
    gpu_count: int = torch.cuda.device_count()
    logger.info(f"GPUが検出されました: {gpu_name} (合計{gpu_count}台)")


def send_completion_notification(
    job_id: str,
    user_id: str,
    user_email: str,
    file_hash: str,
    success: bool,
    error_message: Optional[str] = None,
    processing_time: Optional[float] = None,
    result_path: Optional[str] = None
) -> bool:
    """処理完了通知をPub/Subに送信する"""
    try:
        project_id: str = os.environ.get("GCP_PROJECT_ID")
        pubsub_topic: str = os.environ.get("PUBSUB_TOPIC")
        if not pubsub_topic or not project_id:
            logger.warning("PROJECT_IDまたはPUBSUB_TOPICが設定されていないため、通知を送信できません")
            return False
            
        publisher: pubsub_v1.PublisherClient = pubsub_v1.PublisherClient()
        topic_path: str = publisher.topic_path(project_id, pubsub_topic)
        
        # メッセージデータの準備
        message_data: JobMessageData = JobMessageData(
            job_id=job_id,
            user_id=user_id,
            user_email=user_email,
            file_hash=file_hash,
            event_type="job_completed" if success else "job_failed",
            status="completed" if success else "failed",
            timestamp=datetime.datetime.now().isoformat()
        )
        
        # 辞書に変換
        message_dict: Dict[str, Any] = message_data.model_dump()
        
        # エラーメッセージがある場合は追加
        if error_message:
            message_dict["error_message"] = error_message
            
        # 処理時間と結果パスが提供されている場合は追加
        if processing_time is not None:
            message_dict["processing_time"] = processing_time
            
        if result_path is not None:
            message_dict["result_path"] = result_path
            
        # メッセージをPub/Subに送信
        message_bytes: bytes = json.dumps(message_dict).encode("utf-8")
        future: pubsub_v1.publisher.futures.Future = publisher.publish(topic_path, data=message_bytes)
        message_id: str = future.result()
        
        logger.info("処理完了通知を送信しました: %s", message_id)
        return True
        
    except Exception as e:
        logger.error("処理完了通知の送信エラー: %s", str(e))
        return False


def main() -> None:    # 環境変数から情報を取得
    job_id: str | None = os.environ.get("JOB_ID")
    user_id: str | None = os.environ.get("USER_ID")
    user_email: str | None = os.environ.get("USER_EMAIL")
    gcs_audio_path: str | None = os.environ.get("GCS_AUDIO_PATH")
    file_hash: str | None = os.environ.get("FILE_HASH")
    bucket_name: str | None = os.environ.get("GCS_BUCKET_NAME")
    
    # デバイス設定を環境変数から取得（デフォルトはcuda）
    device: str = os.environ.get("DEVICE", "cuda").lower()
    if device not in ["cpu", "cuda"]:
        logger.warning(f"無効なデバイス指定 '{device}'。'cuda'にデフォルト設定します。")
        device = "cuda"
    
    # GPUを要求されたが利用できない場合の処理
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("GPUが要求されましたが利用できません。CPUにフォールバックします。")
        device = "cpu"
    
    # デバイス情報の表示
    if device == "cuda":
        check_gpu_availability()
        logger.debug("GPUを使用して処理を実行します")
    else:
        logger.debug("CPUを使用して処理を実行します")
    
    # 追加のパラメータを環境変数から取得
    num_speakers: str | None = os.environ.get("NUM_SPEAKERS")
    min_speakers: str = os.environ.get("MIN_SPEAKERS", "1")
    max_speakers: str = os.environ.get("MAX_SPEAKERS", "1")
    language: str = os.environ.get("LANGUAGE", "ja")
    initial_prompt: str = os.environ.get("INITIAL_PROMPT", "")
    
    if not job_id or not user_id or not gcs_audio_path or not file_hash or not bucket_name:
        raise ValueError("必要な環境変数が設定されていません")
    
    # 処理開始時間
    total_start_time: float = time.time()
    
    logger.info(f"処理開始: ジョブID={job_id}, ユーザーID={user_id}, hash={file_hash}")
    
    try:
        # GPUが利用可能かチェック
        check_gpu_availability()
        
        # 入出力ファイルのパスを準備
        base_dir: str = f"whisper/{user_id}/{file_hash}"
        temp_wav_path: str = f"temp_{file_hash}.wav"
        transcription_json: str = f"temp_{file_hash}_transcription.json"
        diarization_json: str = f"temp_{file_hash}_diarization.json"
        
        # 出力先のGCSパス
        output_gcs_path: str = f"gs://{bucket_name}/{base_dir}/transcription.json"
        
        try:
            # ステップ1: 音声変換
            logger.info("=== Step 1: Converting audio to WAV format ===")
            step1_start_time: float = time.time()
            convert_cmd: list[str] = [
                "python3", "convert_audio.py",
                gcs_audio_path,
                temp_wav_path,
                "--device", device
            ]
            subprocess.run(convert_cmd, check=True)
            step1_duration: float = time.time() - step1_start_time
            logger.info(f"Step 1 completed in {step1_duration:.2f} seconds")
            
            # ステップ2: 文字起こし
            logger.info("\n=== Step 2: Running transcription ===")
            step2_start_time: float = time.time()
            transcribe_cmd: list[str] = [
                "python3", "transcribe.py",
                temp_wav_path,
                transcription_json,
                "--device", device
            ]
            # 言語とプロンプトが指定されていれば追加
            if language:
                transcribe_cmd.extend(["--language", language])
            if initial_prompt:
                transcribe_cmd.extend(["--initial-prompt", initial_prompt])
                
            subprocess.run(transcribe_cmd, check=True)
            step2_duration: float = time.time() - step2_start_time
            logger.info(f"Step 2 completed in {step2_duration:.2f} seconds")
            
            # HF_AUTH_TOKENを環境変数から取得
            hf_auth_token: str | None = os.environ.get("HF_AUTH_TOKEN")
            if not hf_auth_token:
                raise ValueError("HF_AUTH_TOKEN環境変数が設定されていません")
            
            # ステップ3: 話者分離
            logger.info("\n=== Step 3: Running speaker diarization ===")
            step3_start_time: float = time.time()
            diarize_cmd: list[str] = [
                "python3", "diarize.py",
                temp_wav_path,
                diarization_json,
                hf_auth_token,
                "--device", device
            ]
            
            # 話者数の指定（環境変数から取得）
            if num_speakers and num_speakers.strip():
                diarize_cmd.extend(["--num-speakers", num_speakers])
            else:
                # デフォルトまたは環境変数のmin/max話者数
                diarize_cmd.extend(["--min-speakers", min_speakers, "--max-speakers", max_speakers])
            
            subprocess.run(diarize_cmd, check=True)
            step3_duration: float = time.time() - step3_start_time
            logger.info(f"Step 3 completed in {step3_duration:.2f} seconds")
            
            # ステップ4: 結果の結合
            logger.info("\n=== Step 4: Combining results ===")
            step4_start_time: float = time.time()
            combine_cmd: list[str] = [
                "python3", "combine_results.py",
                transcription_json,
                diarization_json,
                output_gcs_path
            ]
            subprocess.run(combine_cmd, check=True)
            step4_duration: float = time.time() - step4_start_time
            logger.info(f"Step 4 completed in {step4_duration:.2f} seconds")
            
            # 全体処理時間
            total_duration: float = time.time() - total_start_time
            
            # 各ステップの処理時間サマリー
            logger.info("\n=== Processing Time Summary ===")
            logger.info(f"Step 1 (Audio Conversion): {step1_duration:.2f} seconds")
            logger.info(f"Step 2 (Transcription): {step2_duration:.2f} seconds")
            logger.info(f"Step 3 (Speaker Diarization): {step3_duration:.2f} seconds")
            logger.info(f"Step 4 (Combining Results): {step4_duration:.2f} seconds")
            logger.info(f"Total processing time: {total_duration:.2f} seconds")
            
            logger.info(f"\nFinal results saved to {output_gcs_path}")
            
            # 処理完了通知を送信
            send_completion_notification(
                job_id, 
                user_id, 
                user_email, 
                file_hash, 
                True, 
                processing_time=total_duration, 
                result_path=output_gcs_path
            )
            
        except Exception as process_error:
            # 処理中のエラーを記録
            error_message: str = str(process_error)
            logger.error(f"処理エラー: {error_message}")
            
            # エラー通知を送信
            send_completion_notification(
                job_id, 
                user_id, 
                user_email, 
                file_hash, 
                False, 
                error_message=error_message
            )
            raise process_error
            
        finally:
            # 中間ファイルを削除
            logger.info("\nCleaning up temporary files...")
            temp_files: list[str] = [temp_wav_path, transcription_json, diarization_json]
            for file_path in temp_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Removed: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to remove {file_path}: {e}")
    
    except Exception as e:
        # 全体的なエラーを記録
        error_message: str = str(e)
        logger.error(f"処理エラー: {error_message}")
        
        # エラー通知を送信
        send_completion_notification(
            job_id, 
            user_id, 
            user_email, 
            file_hash, 
            False, 
            error_message=error_message
        )
        raise e
  if __name__ == "__main__":
      # CLIでも呼び出せるように引数解析を追加
      parser: argparse.ArgumentParser = argparse.ArgumentParser(description='音声文字起こしと話者分離のバッチ処理')
      parser.add_argument(
          '--device', 
          choices=['cpu', 'cuda'], 
          default='cuda', 
          help='使用するデバイス (CPU または CUDA GPU)'
      )
      args: argparse.Namespace = parser.parse_args()
    
      # 環境変数にデバイス情報を設定
      os.environ["DEVICE"] = args.device
    
      main()
