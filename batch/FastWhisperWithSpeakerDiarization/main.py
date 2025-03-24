import argparse
import os
import subprocess
import time
from pathlib import Path

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

def main():
    parser = argparse.ArgumentParser(description='音声ファイルの文字起こしと話者分離を実行する統合スクリプト')
    parser.add_argument('audio_path', help='音声ファイルのパス (ローカルまたはGCS)')
    parser.add_argument('output_file', help='出力CSVファイルのパス (ローカルまたはGCS)')
    parser.add_argument('--min-speakers', type=int, help='最小話者数')
    parser.add_argument('--max-speakers', type=int, help='最大話者数')
    parser.add_argument('--num-speakers', type=int, help='固定話者数 (min/maxよりも優先)')
    parser.add_argument('-d', '--debug', action='store_true', help='デバッグモード (中間ファイルを保持)')
    args = parser.parse_args()

    # 処理開始時間
    total_start_time = time.time()
    
    # 入出力ファイルのパスを準備
    base_name = Path(args.audio_path).stem
    temp_wav_path = f"temp_{base_name}.wav"
    transcription_csv = f"temp_{base_name}_transcription.csv"
    diarization_csv = f"temp_{base_name}_diarization.csv"
    
    try:
        # ステップ1: 音声変換
        print("=== Step 1: Converting audio to WAV format ===")
        convert_cmd = [
            "python3", "convert_audio.py",
            args.audio_path,
            temp_wav_path
        ]
        subprocess.run(convert_cmd, check=True)
        
        # ステップ2: 文字起こし
        print("\n=== Step 2: Running transcription ===")
        transcribe_cmd = [
            "python3", "transcribe.py",
            temp_wav_path,
            transcription_csv
        ]
        subprocess.run(transcribe_cmd, check=True)
        
        # ステップ3: 話者分離
        print("\n=== Step 3: Running speaker diarization ===")
        diarize_cmd = [
            "python3", "diarize.py",
            temp_wav_path,
            diarization_csv
        ]
        if args.min_speakers:
            diarize_cmd.extend(["--min-speakers", str(args.min_speakers)])
        if args.max_speakers:
            diarize_cmd.extend(["--max-speakers", str(args.max_speakers)])
        if args.num_speakers:
            diarize_cmd.extend(["--num-speakers", str(args.num_speakers)])
        
        subprocess.run(diarize_cmd, check=True)
        
        # ステップ4: 結果の結合
        print("\n=== Step 4: Combining results ===")
        combine_cmd = [
            "python3", "combine_results.py",
            transcription_csv,
            diarization_csv,
            args.output_file
        ]
        subprocess.run(combine_cmd, check=True)
        
        print(f"\nTotal processing completed in {time.time() - total_start_time:.2f} seconds")
        print(f"Final results saved to {args.output_file}")
        
    finally:
        # デバッグモードでない場合は中間ファイルを削除
        if not args.debug:
            print("\nCleaning up temporary files...")
            temp_files = [temp_wav_path, transcription_csv, diarization_csv]
            for file_path in temp_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"Removed: {file_path}")
                except Exception as e:
                    print(f"Failed to remove {file_path}: {e}")
        else:
            print("\nDebug mode: Keeping temporary files:")
            print(f"- Audio: {temp_wav_path}")
            print(f"- Transcription: {transcription_csv}")
            print(f"- Diarization: {diarization_csv}")

if __name__ == "__main__":
    main()