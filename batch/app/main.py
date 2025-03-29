import argparse
import os
import subprocess
import time
import torch
from pathlib import Path
from google.cloud import firestore
from google.cloud import storage
from google.cloud import pubsub_v1
import json
import datetime
from dotenv import load_dotenv

# 環境変数ファイルが存在する場合のみ読み込む
config_path = 'config/.env'
config_develop_path = 'config_develop/.env.develop'

load_dotenv(config_path)

if os.path.exists(config_develop_path):
    load_dotenv(config_develop_path)


def is_gcs_path(path):
    """GCSパスかどうかを判定する"""
    return path.startswith("gs://")

def get_local_path(gcs_path):
    """GCSパスからローカル一時ファイルパスを生成する"""
    if not is_gcs_path(gcs_path):
        return gcs_path
    
    path_without_prefix = gcs_path[5:]
    parts = path_without_prefix.split("/")
    bucket_name = parts[0]
    file_name = parts[-1]
    return f"temp_{bucket_name}_{file_name}"

def check_gpu_availability():
    """GPUが利用可能かどうかを確認する"""
    if not torch.cuda.is_available():
        raise Exception("GPU環境が検出されませんでした。このスクリプトはGPU環境でのみ実行できます。")
    
    gpu_name = torch.cuda.get_device_name(0)
    gpu_count = torch.cuda.device_count()
    print(f"GPUが検出されました: {gpu_name} (合計{gpu_count}台)")

def send_completion_notification(job_id, user_id, user_email, file_hash, success, error_message=None):
    """処理完了通知をPub/Subに送信する"""
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        pubsub_topic = os.environ.get("PUBSUB_TOPIC")
        if not pubsub_topic or not project_id:
            print("PROJECT_IDまたはPUBSUB_TOPICが設定されていないため、通知を送信できません")
            return False
            
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, pubsub_topic)
        
        # メッセージデータの準備
        message_data = {
            "job_id": job_id,
            "user_id": user_id,
            "event_type": "batch_complete",
            "success": success
        }
        # エラーメッセージがある場合は追加
        if error_message:
            message_data["error_message"] = error_message
            
        # メッセージをPub/Subに送信
        message_bytes = json.dumps(message_data).encode("utf-8")
        future = publisher.publish(topic_path, data=message_bytes)
        message_id = future.result()
        
        print(f"処理完了通知を送信しました: {message_id}")
        return True
        
    except Exception as e:
        print(f"処理完了通知の送信エラー: {str(e)}")
        return False

def main():
    # 環境変数から情報を取得
    job_id = os.environ.get("JOB_ID")
    user_id = os.environ.get("USER_ID")
    user_email = os.environ.get("USER_EMAIL")
    gcs_audio_path = os.environ.get("GCS_AUDIO_PATH")
    file_hash = os.environ.get("FILE_HASH")
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    
    # 追加のパラメータを環境変数から取得
    num_speakers = os.environ.get("NUM_SPEAKERS")
    min_speakers = os.environ.get("MIN_SPEAKERS", "1")
    max_speakers = os.environ.get("MAX_SPEAKERS", "6")
    language = os.environ.get("LANGUAGE", "ja")
    initial_prompt = os.environ.get("INITIAL_PROMPT", "")
    
    if not job_id or not user_id or not gcs_audio_path or not file_hash or not bucket_name:
        raise ValueError("必要な環境変数が設定されていません")
    
    # 処理開始時間
    total_start_time = time.time()
    
    # 処理開始通知
    send_progress_notification(job_id, user_id, user_email, file_hash, "processing", 5)
    print(f"処理開始: ジョブID={job_id}, ユーザーID={user_id}, hash={file_hash}")
    
    try:
        # GPUが利用可能かチェック
        check_gpu_availability()
        send_progress_notification(job_id, user_id, user_email, file_hash, "processing", 10)
        
        # 以下、元の処理フロー（Firestoreへの直接更新を除去）
        # 入出力ファイルのパスを準備
        base_dir = f"whisper/{user_id}/{file_hash}"
        temp_wav_path = f"temp_{file_hash}.wav"
        transcription_json = f"temp_{file_hash}_transcription.json"
        diarization_json = f"temp_{file_hash}_diarization.json"
        
        # 出力先のGCSパス
        output_gcs_path = f"gs://{bucket_name}/{base_dir}/transcription.json"
        
        try:
            # ステップ1: 音声変換
            print("=== Step 1: Converting audio to WAV format with GPU acceleration ===")
            step1_start_time = time.time()
            convert_cmd = [
                "python3", "convert_audio.py",
                gcs_audio_path,
                temp_wav_path
            ]
            subprocess.run(convert_cmd, check=True)
            step1_duration = time.time() - step1_start_time
            print(f"Step 1 completed in {step1_duration:.2f} seconds")
            send_progress_notification(job_id, user_id, user_email, file_hash, "processing", 30)
            
            # ステップ2: 文字起こし
            print("\n=== Step 2: Running transcription using GPU ===")
            step2_start_time = time.time()
            transcribe_cmd = [
                "python3", "transcribe.py",
                temp_wav_path,
                transcription_json
            ]
            # 言語とプロンプトが指定されていれば追加
            if language:
                transcribe_cmd.extend(["--language", language])
            if initial_prompt:
                transcribe_cmd.extend(["--initial-prompt", initial_prompt])
                
            subprocess.run(transcribe_cmd, check=True)
            step2_duration = time.time() - step2_start_time
            print(f"Step 2 completed in {step2_duration:.2f} seconds")
            send_progress_notification(job_id, user_id, user_email, file_hash, "processing", 60)
            
            # HF_AUTH_TOKENを環境変数から取得
            hf_auth_token = os.environ.get("HF_AUTH_TOKEN")
            if not hf_auth_token:
                raise ValueError("HF_AUTH_TOKEN環境変数が設定されていません")
            
            # ステップ3: 話者分離
            print("\n=== Step 3: Running speaker diarization on GPU ===")
            step3_start_time = time.time()
            diarize_cmd = [
                "python3", "diarize.py",
                temp_wav_path,
                diarization_json,
                hf_auth_token
            ]
            
            # 話者数の指定（環境変数から取得）
            if num_speakers and num_speakers.strip():
                diarize_cmd.extend(["--num-speakers", num_speakers])
            else:
                # デフォルトまたは環境変数のmin/max話者数
                diarize_cmd.extend(["--min-speakers", min_speakers, "--max-speakers", max_speakers])
            
            subprocess.run(diarize_cmd, check=True)
            step3_duration = time.time() - step3_start_time
            print(f"Step 3 completed in {step3_duration:.2f} seconds")
            send_progress_notification(job_id, user_id, user_email, file_hash, "processing", 90)
            
            # ステップ4: 結果の結合
            print("\n=== Step 4: Combining results ===")
            step4_start_time = time.time()
            combine_cmd = [
                "python3", "combine_results.py",
                transcription_json,
                diarization_json,
                output_gcs_path
            ]
            subprocess.run(combine_cmd, check=True)
            step4_duration = time.time() - step4_start_time
            print(f"Step 4 completed in {step4_duration:.2f} seconds")
            
            # 全体処理時間
            total_duration = time.time() - total_start_time
            
            # 各ステップの処理時間サマリー
            print("\n=== Processing Time Summary ===")
            print(f"Step 1 (Audio Conversion): {step1_duration:.2f} seconds")
            print(f"Step 2 (Transcription): {step2_duration:.2f} seconds")
            print(f"Step 3 (Speaker Diarization): {step3_duration:.2f} seconds")
            print(f"Step 4 (Combining Results): {step4_duration:.2f} seconds")
            print(f"Total processing time: {total_duration:.2f} seconds")
            
            print(f"\nFinal results saved to {output_gcs_path}")
            
            # 処理完了通知を送信
            send_completion_notification(job_id, user_id, user_email, file_hash, True, 
                                        processing_time=total_duration, 
                                        result_path=output_gcs_path)
            
        except Exception as process_error:
            # 処理中のエラーを記録
            error_message = str(process_error)
            print(f"処理エラー: {error_message}")
            
            # エラー通知を送信
            send_completion_notification(job_id, user_id, user_email, file_hash, False, error_message=error_message)
            raise process_error
            
        finally:
            # 中間ファイルを削除
            print("\nCleaning up temporary files...")
            temp_files = [temp_wav_path, transcription_json, diarization_json]
            for file_path in temp_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"Removed: {file_path}")
                except Exception as e:
                    print(f"Failed to remove {file_path}: {e}")
    
    except Exception as e:
        # 全体的なエラーを記録
        error_message = str(e)
        print(f"処理エラー: {error_message}")
        
        # エラー通知を送信
        send_completion_notification(job_id, user_id, user_email, file_hash, False, error_message=error_message)
        raise e

# 進捗通知を送信する関数
def send_progress_notification(job_id, user_id, user_email, file_hash, status, progress):
    """処理進捗通知をPub/Subに送信する"""
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        pubsub_topic = os.environ.get("PUBSUB_TOPIC")
        if not pubsub_topic or not project_id:
            print("PROJECT_IDまたはPUBSUB_TOPICが設定されていないため、通知を送信できません")
            return False
            
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, pubsub_topic)
        
        # メッセージデータの準備
        message_data = {
            "job_id": job_id,
            "user_id": user_id,
            "user_email": user_email,
            "file_hash": file_hash,
            "event_type": "progress_update",
            "status": status,
            "progress": progress,
            "timestamp": datetime.datetime.now().isoformat()
        }
            
        # メッセージをPub/Subに送信
        message_bytes = json.dumps(message_data).encode("utf-8")
        future = publisher.publish(topic_path, data=message_bytes)
        message_id = future.result()
        
        print(f"進捗通知を送信しました: {progress}%, message_id: {message_id}")
        return True
        
    except Exception as e:
        print(f"進捗通知の送信エラー: {str(e)}")
        return False

if __name__ == "__main__":
    main()