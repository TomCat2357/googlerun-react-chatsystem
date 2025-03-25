import argparse
import time
import torch
import torchaudio
import pandas as pd
import os
import io
from google.cloud import storage
import csv
from pyannote.audio import Pipeline

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

def diarize_audio(audio_path, output_csv, hf_auth_token, min_speakers=None, max_speakers=None, num_speakers=None):
    """音声ファイルの話者分け（ダイアリゼーション）を実行してCSVに保存する"""
    now = time.time()
    
    try:
        # GPUの設定
        device = torch.device("cuda")
        print("Using GPU for diarization")
        
        # pyannoteのパイプライン設定
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_auth_token
        )
        
        # デバイス設定（常にGPUを使用）
        pipeline.to(device)
        
        # 音声ファイルを読み込む
        waveform, sample_rate = torchaudio.load(audio_path)
        
        # ダイアリゼーションパラメータの設定
        diarization_params = {}
        
        if num_speakers is not None:
            diarization_params["num_speakers"] = num_speakers
        else:
            if min_speakers is not None:
                diarization_params["min_speakers"] = min_speakers
            if max_speakers is not None:
                diarization_params["max_speakers"] = max_speakers
        
        # 話者分け（ダイアリゼーション）の実行
        diarization = pipeline(
            {"waveform": waveform, "sample_rate": sample_rate},
            **diarization_params
        )
        
        # 結果をデータフレームに変換
        data = []
        for segment, _, speaker in diarization.itertracks(yield_label=True):
            data.append({
                "start": segment.start,
                "end": segment.end,
                "speaker": speaker
            })
        
        # Pandasデータフレームに変換
        df = pd.DataFrame(data)
        
        # CSVとして保存
        save_dataframe(df, output_csv)
        
        print(f"Speaker diarization (GPU) completed in {time.time() - now:.2f} seconds")
        return df
        
    except Exception as e:
        print(f"Error during diarization on GPU: {e}")
        raise Exception(f"GPUでの実行に失敗しました: {e}")

def main():
    parser = argparse.ArgumentParser(description='音声ファイルの話者分離を実行する')
    parser.add_argument('audio_path', help='音声ファイルのパス (WAV形式)')
    parser.add_argument('output_csv', help='出力CSVファイルのパス')
    parser.add_argument('hf_auth_token', help='HuggingFace認証トークン (必須)')
    parser.add_argument('--min-speakers', type=int, help='最小話者数')
    parser.add_argument('--max-speakers', type=int, help='最大話者数')
    parser.add_argument('--num-speakers', type=int, help='固定話者数（min/maxよりも優先）')
    args = parser.parse_args()
    
    # GPUが使用可能かチェック
    if not torch.cuda.is_available():
        raise Exception("GPUが利用できません。このスクリプトはGPU環境でのみ実行できます。")
    
    diarize_audio(
        args.audio_path, 
        args.output_csv,
        args.hf_auth_token,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        num_speakers=args.num_speakers
    )

if __name__ == "__main__":
    main()
