import time
import io
import tempfile
import os
from google.cloud import storage
from pyannote.audio import Pipeline
import torch
import torchaudio
import polars as pl

# GCSからファイルをバイトとして取得する関数
def get_gcs_file_bytes(gcs_uri):
    """Reads a file from GCS as bytes without saving to disk."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError("URI must start with gs://")
    
    # Remove 'gs://' prefix and split into bucket and blob path
    path_without_prefix = gcs_uri[5:]
    bucket_name, blob_path = path_without_prefix.split("/", 1)
    
    # Get the file content
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    # Download into memory
    in_memory_file = io.BytesIO()
    blob.download_to_file(in_memory_file)
    in_memory_file.seek(0)  # Reset the file pointer to the beginning
    
    print(f"Loaded {gcs_uri} into memory")
    return in_memory_file

def run_speaker_diarization(gcs_uri, output_csv="speaker_diarization_results.csv"):
    """
    GCSから音声ファイルを取得し、話者分け（ダイアリゼーション）を実行して結果をCSVに保存する
    
    Args:
        gcs_uri: GCS上の音声ファイルのURI (gs://bucket/path/to/file.wav)
        output_csv: 結果を保存するCSVファイルのパス
    
    Returns:
        Polarsデータフレーム: 話者分けの結果
    """
    now = time.time()
    
    # GCSからファイルを取得
    audio_bytes = get_gcs_file_bytes(gcs_uri)
    
    # 一時ファイルに保存（torchaudioが読み込めるように）
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_filename = temp_file.name
    temp_file.close()
    
    # バイトを一時ファイルに書き込む
    with open(temp_filename, 'wb') as f:
        f.write(audio_bytes.getvalue())
    
    # pyannoteのパイプライン設定
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token="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"
    )
    
    # GPU設定
    pipeline.to(torch.device("cuda"))
    
    # 音声ファイルを読み込む
    waveform, sample_rate = torchaudio.load(temp_filename)
    
    # 話者分け（ダイアリゼーション）の実行
    diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate})
    
    # 一時ファイルを削除
    os.unlink(temp_filename)
    
    # 結果をデータフレームに変換
    data = []
    for segment, _, speaker in diarization.itertracks(yield_label=True):
        data.append({
            "start": segment.start,
            "end": segment.end,
            "speaker": speaker
        })
    
    # Polarsデータフレームに変換
    df = pl.DataFrame(data)
    
    # CSVとして保存
    df.write_csv(output_csv)
    
    print(f"Speaker diarization completed in {time.time() - now:.2f} seconds")
    print(f"Results saved to {output_csv}")
    
    return df

# スクリプトとして実行された場合のサンプル使用法
if __name__ == "__main__":
    gcs_uri = "gs://storage_music_test_20250319/sample1.wav"
    result_df = run_speaker_diarization(gcs_uri)
    print(result_df)
