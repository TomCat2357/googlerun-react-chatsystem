import argparse
import pandas as pd
import os
import io
from google.cloud import storage
import json

def is_gcs_path(path):
    """GCSパスかどうかを判定する"""
    return str(path).startswith("gs://")

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

def read_json(file_path):
    """JSONファイルを読み込む（GCSまたはローカル）"""
    if is_gcs_path(file_path):
        # GCSからJSONを読み込む
        path_without_prefix = file_path[5:]
        bucket_name, blob_path = path_without_prefix.split("/", 1)
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        content = blob.download_as_text()
        return pd.read_json(io.StringIO(content), orient="records")
    else:
        # ローカルからJSONを読み込む
        return pd.read_json(file_path, orient="records")

def combine_results(transcription_json, diarization_json, output_json):
    """文字起こしと話者分離の結果を結合する"""
    # JSONファイルを読み込む
    transcription_df = read_json(transcription_json)
    speaker_df = read_json(diarization_json)
    
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
    
    # JSONとして保存
    save_dataframe(result_df, output_json)
    
    print("Results combined successfully")
    return result_df

def main():
    parser = argparse.ArgumentParser(description='文字起こしと話者分離の結果を結合する')
    parser.add_argument('transcription_json', help='文字起こし結果のJSONファイルパス')
    parser.add_argument('diarization_json', help='話者分離結果のJSONファイルパス')
    parser.add_argument('output_json', help='結合結果を保存するJSONファイルパス')
    args = parser.parse_args()
    
    combine_results(args.transcription_json, args.diarization_json, args.output_json)

if __name__ == "__main__":
    main()