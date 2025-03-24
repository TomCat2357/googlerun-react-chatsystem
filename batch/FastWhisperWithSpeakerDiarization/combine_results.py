import argparse
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

def read_csv(file_path):
    """CSVファイルを読み込む（GCSまたはローカル）"""
    if is_gcs_path(file_path):
        # GCSからCSVを読み込む
        path_without_prefix = file_path[5:]
        bucket_name, blob_path = path_without_prefix.split("/", 1)
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        content = blob.download_as_text()
        return pd.read_csv(io.StringIO(content))
    else:
        # ローカルからCSVを読み込む
        return pd.read_csv(file_path)

def combine_results(transcription_csv, diarization_csv, output_csv):
    """文字起こしと話者分離の結果を結合する"""
    # CSVファイルを読み込む
    transcription_df = read_csv(transcription_csv)
    speaker_df = read_csv(diarization_csv)
    
    # 結果を格納する新しいデータフレームの作成
    result_df = transcription_df.copy()
    result_df['speaker'] = None
    
    # 各文字起こしセグメントに対する話者の判定
    for i, trans_row in transcription_df.iterrows():
        trans_start = trans_row['start']
        trans_end = trans_row['end']
        
        # 話者データフレームから重複する時間範囲のセグメントを抽出
        overlapping_speakers = speaker_df[
            ((speaker_df['start'] <= trans_end) & (speaker_df['end'] >= trans_start))
        ]
        
        if len(overlapping_speakers) == 0:
            continue
        
        # 各話者セグメントと文字起こしセグメントの重複時間を計算
        speaker_overlaps = {}
        for _, spk_row in overlapping_speakers.iterrows():
            spk_start = spk_row['start']
            spk_end = spk_row['end']
            speaker = spk_row['speaker']
            
            # 重複時間の計算
            overlap_start = max(trans_start, spk_start)
            overlap_end = min(trans_end, spk_end)
            overlap_duration = overlap_end - overlap_start
            
            if speaker not in speaker_overlaps:
                speaker_overlaps[speaker] = 0
            speaker_overlaps[speaker] += overlap_duration
        
        # 最も重複時間が長い話者を選択
        if speaker_overlaps:
            best_speaker = max(speaker_overlaps.items(), key=lambda x: x[1])[0]
            result_df.at[i, 'speaker'] = best_speaker
    
    # CSVとして保存
    save_dataframe(result_df, output_csv)
    
    print("Results combined successfully")
    return result_df

def main():
    parser = argparse.ArgumentParser(description='文字起こしと話者分離の結果を結合する')
    parser.add_argument('transcription_csv', help='文字起こし結果のCSVファイルパス')
    parser.add_argument('diarization_csv', help='話者分離結果のCSVファイルパス')
    parser.add_argument('output_csv', help='結合結果を保存するCSVファイルパス')
    args = parser.parse_args()
    
    combine_results(args.transcription_csv, args.diarization_csv, args.output_csv)

if __name__ == "__main__":
    main()