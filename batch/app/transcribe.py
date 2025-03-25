import argparse
import time
from faster_whisper import WhisperModel
import pandas as pd
import os
import io
from google.cloud import storage
import csv

def is_gcs_path(path):
    """GCSパスかどうかを判定する"""
    return path.startswith("gs://")

def save_dataframe_to_local(df, output_path):
    """データフレームをローカルファイルとして保存する"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)
    print(f"Results saved to local file: {output_path}")

def save_dataframe_to_gcs(df, gcs_uri):
    """データフレームをGCSに保存する"""
    # CSVをメモリ内に作成
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, quoting=csv.QUOTE_ALL)
    csv_content = csv_buffer.getvalue()
    
    # GCSに保存
    path_without_prefix = gcs_uri[5:]
    bucket_name, blob_path = path_without_prefix.split("/", 1)
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    blob.upload_from_string(csv_content, content_type='text/csv')
    print(f"Results saved to GCS: {gcs_uri}")

def save_dataframe(df, output_path):
    """データフレームをGCSまたはローカルに保存する"""
    if is_gcs_path(output_path):
        save_dataframe_to_gcs(df, output_path)
    else:
        save_dataframe_to_local(df, output_path)

def transcribe_audio(audio_path, output_csv):
    """音声ファイルの文字起こしを実行してCSVに保存する"""
    now = time.time()
    
    print("Initializing Whisper model on GPU...")
    # Whisperモデルの初期化 - GPUが利用可能な場合はGPUを使用
    model = WhisperModel("large", device="cuda")
    
    model_init_time = time.time()
    print(f"Model initialization completed in {model_init_time - now:.2f} seconds")
    
    print("Starting transcription...")
    # 文字起こしの実行
    segments, info = model.transcribe(audio_path, beam_size=5)
    
    # 結果をデータフレームに変換
    data = []
    for segment in segments:
        data.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text
        })
    
    transcription_time = time.time()
    print(f"Core transcription completed in {transcription_time - model_init_time:.2f} seconds")
    
    # Pandasデータフレームに変換
    df = pd.DataFrame(data)
    
    print("Saving results...")
    # CSVとして保存
    save_dataframe(df, output_csv)
    
    save_time = time.time()
    print(f"Results saving completed in {save_time - transcription_time:.2f} seconds")
    
    total_time = time.time() - now
    print(f"Total transcription process completed in {total_time:.2f} seconds")
    return df

def main():
    parser = argparse.ArgumentParser(description='音声ファイルの文字起こしを実行する')
    parser.add_argument('audio_path', help='音声ファイルのパス (WAV形式)')
    parser.add_argument('output_csv', help='出力CSVファイルのパス')
    args = parser.parse_args()
    
    transcribe_audio(args.audio_path, args.output_csv)

if __name__ == "__main__":
    main()
