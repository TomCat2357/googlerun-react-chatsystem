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

def send_completion_notification(job_id, user_id, user_email, success, error_message=None):
    """処理完了通知をPub/Subに送信する"""
    try:
        pubsub_topic = os.environ.get("PUBSUB_TOPIC")
        if not pubsub_topic:
            print("PUBSUB_TOPICが設定されていないため、通知を送信できません")
            return False
            
        publisher = pubsub_v1.PublisherClient()
        
        # メッセージデータの準備
        message_data = {
            "job_id": job_id,
            "user_id": user_id,
            "user_email": user_email,
            "event_type": "batch_complete",
            "success": success
        }
        
        if error_message:
            message_data["error_message"] = error_message
            
        # メッセージをPub/Subに送信
        message_bytes = json.dumps(message_data).encode("utf-8")
        future = publisher.publish(pubsub_topic, data=message_bytes)
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
    
    if not job_id or not user_id or not gcs_audio_path:
        raise ValueError("必要な環境変数(JOB_ID, USER_ID, GCS_AUDIO_PATH)が設定されていません")
    
    # Firestore初期化
    db = firestore.Client()
    job_ref = db.collection("whisper_jobs").document(job_id)
    
    # 処理開始時間
    total_start_time = time.time()
    
    # 処理状態を更新
    try:
        job_data = job_ref.get().to_dict()
        if not job_data:
            raise ValueError(f"ジョブデータが見つかりません: {job_id}")
        
        # バケット名を取得
        bucket_name = gcs_audio_path.split("/")[2] if gcs_audio_path.startswith("gs://") else ""
        
        # 処理開始を記録
        job_ref.update({
            "status": "processing",
            "progress": 5,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        print(f"処理開始: ジョブID={job_id}, ユーザーID={user_id}")
        
        # GPUが利用可能かチェック
        check_gpu_availability()
        job_ref.update({"progress": 10})
        
        # 入出力ファイルのパスを準備
        base_name = Path(gcs_audio_path).stem
        temp_wav_path = f"temp_{base_name}.wav"
        transcription_json = f"temp_{base_name}_transcription.json"
        diarization_json = f"temp_{base_name}_diarization.json"
        
        # 出力先のGCSパス
        output_gcs_path = f"gs://{bucket_name}/whisper/{user_id}/{job_id}/transcription.json"
        
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
            step1_end_time = time.time()
            step1_duration = step1_end_time - step1_start_time
            print(f"Step 1 completed in {step1_duration:.2f} seconds")
            job_ref.update({"progress": 30})
            
            # ステップ2: 文字起こし
            print("\n=== Step 2: Running transcription using GPU ===")
            step2_start_time = time.time()
            transcribe_cmd = [
                "python3", "transcribe.py",
                temp_wav_path,
                transcription_json
            ]
            subprocess.run(transcribe_cmd, check=True)
            step2_end_time = time.time()
            step2_duration = step2_end_time - step2_start_time
            print(f"Step 2 completed in {step2_duration:.2f} seconds")
            job_ref.update({"progress": 60})
            
            # HF_AUTH_TOKENを環境変数から取得
            hf_auth_token = os.environ.get("HF_AUTH_TOKEN")
            if not hf_auth_token:
                raise ValueError("HF_AUTH_TOKEN環境変数が設定されていません")
            
            # ステップ3: 話者分離（常にGPUを使用）
            print("\n=== Step 3: Running speaker diarization on GPU ===")
            step3_start_time = time.time()
            diarize_cmd = [
                "python3", "diarize.py",
                temp_wav_path,
                diarization_json,
                hf_auth_token
            ]
            
            # 話者数の指定（オプション）
            num_speakers = job_data.get("num_speakers")
            if num_speakers:
                diarize_cmd.extend(["--num-speakers", str(num_speakers)])
            else:
                # デフォルトのmin/max話者数
                diarize_cmd.extend(["--min-speakers", "1", "--max-speakers", "6"])
            
            subprocess.run(diarize_cmd, check=True)
            step3_end_time = time.time()
            step3_duration = step3_end_time - step3_start_time
            print(f"Step 3 completed in {step3_duration:.2f} seconds")
            job_ref.update({"progress": 90})
            
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
            step4_end_time = time.time()
            step4_duration = step4_end_time - step4_start_time
            print(f"Step 4 completed in {step4_duration:.2f} seconds")
            
            # 全体処理時間
            total_duration = time.time() - total_start_time
            
            # 処理成功を記録
            job_ref.update({
                "status": "completed",
                "progress": 100,
                "result_path": output_gcs_path,
                "processing_time": total_duration,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
            # 各ステップの処理時間サマリー
            print("\n=== Processing Time Summary ===")
            print(f"Step 1 (Audio Conversion): {step1_duration:.2f} seconds")
            print(f"Step 2 (Transcription): {step2_duration:.2f} seconds")
            print(f"Step 3 (Speaker Diarization): {step3_duration:.2f} seconds")
            print(f"Step 4 (Combining Results): {step4_duration:.2f} seconds")
            print(f"Total processing time: {total_duration:.2f} seconds")
            
            print(f"\nFinal results saved to {output_gcs_path}")
            
            # 処理完了通知を送信
            send_completion_notification(job_id, user_id, user_email, True)
            
        except Exception as process_error:
            # 処理中のエラーを記録
            error_message = str(process_error)
            job_ref.update({
                "status": "failed",
                "error_message": error_message,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"処理エラー: {error_message}")
            
            # エラー通知を送信
            send_completion_notification(job_id, user_id, user_email, False, error_message)
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
        try:
            job_ref.update({
                "status": "failed",
                "error_message": error_message,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
            # エラー通知を送信
            send_completion_notification(job_id, user_id, user_email, False, error_message)
            
        except Exception as update_error:
            print(f"Firestore更新エラー: {str(update_error)}")
        
        print(f"処理エラー: {error_message}")
        raise e

if __name__ == "__main__":
    main()