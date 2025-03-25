import argparse
import time
import torch
import torchaudio
import pandas as pd
import os
import io
from google.cloud import storage
import json
from pyannote.audio import Pipeline

def is_gcs_path(path):
    """GCSパスかどうかを判定する"""
    return path.startswith("gs://")

def save_dataframe_to_local(df, output_path):
    """データフレームをローカルJSONファイルとして保存する"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    df.to_json(output_path, orient="records", indent=2)
    print(f"Results saved to local file: {output_path}")

def save_dataframe_to_gcs(df, gcs_uri):
    """データフレームをGCSのJSONに保存する"""
    # JSONをメモリ内に作成
    json_content = df.to_json(orient="records", indent=2)
    
    # GCSに保存
    path_without_prefix = gcs_uri[5:]
    bucket_name, blob_path = path_without_prefix.split("/", 1)
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    blob.upload_from_string(json_content, content_type='application/json')
    print(f"Results saved to GCS: {gcs_uri}")

def save_dataframe(df, output_path):
    """データフレームをGCSまたはローカルに保存する"""
    if is_gcs_path(output_path):
        save_dataframe_to_gcs(df, output_path)
    else:
        save_dataframe_to_local(df, output_path)

def diarize_audio(audio_path, output_json, hf_auth_token, min_speakers=None, max_speakers=None, num_speakers=None):
    """音声ファイルの話者分け（ダイアリゼーション）を実行してJSONに保存する"""
    start_time = time.time()
    
    try:
        # GPUの設定
        device = torch.device("cuda")
        print("Using GPU for diarization")
        
        print("Initializing pyannote pipeline...")
        pipeline_start_time = time.time()
        # pyannoteのパイプライン設定
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_auth_token
        )
        
        # デバイス設定（常にGPUを使用）
        pipeline.to(device)
        pipeline_init_time = time.time() - pipeline_start_time
        print(f"Pipeline initialization completed in {pipeline_init_time:.2f} seconds")
        
        # 音声ファイルを読み込む
        print("Loading audio file...")
        load_start_time = time.time()
        waveform, sample_rate = torchaudio.load(audio_path)
        load_time = time.time() - load_start_time
        print(f"Audio loading completed in {load_time:.2f} seconds")
        
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
        print("Running speaker diarization...")
        diarize_start_time = time.time()
        diarization = pipeline(
            {"waveform": waveform, "sample_rate": sample_rate},
            **diarization_params
        )
        diarize_time = time.time() - diarize_start_time
        print(f"Core diarization completed in {diarize_time:.2f} seconds")
        
        # 結果をデータフレームに変換
        print("Processing results...")
        process_start_time = time.time()
        data = []
        for segment, _, speaker in diarization.itertracks(yield_label=True):
            data.append({
                "start": segment.start,
                "end": segment.end,
                "speaker": speaker
            })
        
        # Pandasデータフレームに変換
        df = pd.DataFrame(data)
        process_time = time.time() - process_start_time
        print(f"Results processing completed in {process_time:.2f} seconds")
        
        # JSONとして保存
        print("Saving results to JSON...")
        save_start_time = time.time()
        save_dataframe(df, output_json)
        save_time = time.time() - save_start_time
        print(f"Results saving completed in {save_time:.2f} seconds")
        
        total_time = time.time() - start_time
        print(f"Speaker diarization (GPU) completed in {total_time:.2f} seconds")
        
        # 時間の内訳を表示
        print("\n=== Diarization Time Breakdown ===")
        print(f"Pipeline initialization: {pipeline_init_time:.2f} seconds")
        print(f"Audio loading: {load_time:.2f} seconds")
        print(f"Core diarization: {diarize_time:.2f} seconds")
        print(f"Results processing: {process_time:.2f} seconds")
        print(f"Results saving: {save_time:.2f} seconds")
        print(f"Total: {total_time:.2f} seconds")
        
        return df
        
    except Exception as e:
        error_time = time.time() - start_time
        print(f"Error during diarization on GPU after {error_time:.2f} seconds: {e}")
        raise Exception(f"GPUでの実行に失敗しました: {e}")

def main():
    parser = argparse.ArgumentParser(description='音声ファイルの話者分離を実行する')
    parser.add_argument('audio_path', help='音声ファイルのパス (WAV形式)')
    parser.add_argument('output_json', help='出力JSONファイルのパス')
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
        args.output_json,
        args.hf_auth_token,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        num_speakers=args.num_speakers
    )

if __name__ == "__main__":
    main()