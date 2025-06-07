import argparse
import time
from faster_whisper import WhisperModel
import pandas as pd
import os
import io
from google.cloud import storage
import json
import torch
import logging
from common_utils.logger import logger

# グローバルなWhisperモデル - プロセス起動時に1度だけ初期化
_GLOBAL_WHISPER_MODEL = None

def _get_whisper_model(device="cuda"):
    """
    グローバルWhisperモデルを取得または初期化する
    
    Args:
        device (str): 使用するデバイス("cuda"または"cpu")
        
    Returns:
        WhisperModel: 初期化済みのWhisperモデル
    """
    global _GLOBAL_WHISPER_MODEL
    
    if _GLOBAL_WHISPER_MODEL is None:
        logger.info(f"初回呼び出し：WhisperモデルをDevice={device}で初期化します")
        start_time = time.time()
        
        # CUDA利用可能かチェック
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA要求されましたが利用できません。CPUにフォールバックします。")
            device = "cpu"
            
        # モデル初期化
        _GLOBAL_WHISPER_MODEL = WhisperModel("large", device=device)
        
        elapsed = time.time() - start_time
        logger.info(f"Whisperモデルの初期化完了しました（{elapsed:.2f}秒）")
    
    return _GLOBAL_WHISPER_MODEL

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

def transcribe_audio(audio_path, output_json, device="cuda", job_id=None, language="ja", initial_prompt=""):
    """音声ファイルの文字起こしを実行してJSONに保存する"""
    now = time.time()
    log_prefix = f"JOB {job_id} " if job_id else ""
    
    # グローバルモデルを取得（初回時は初期化される）
    model = _get_whisper_model(device)
    
    logger.info(f"{log_prefix}文字起こし開始: {audio_path} (言語: {language})")
    
    # 文字起こしオプションの準備
    transcribe_options = {
        "beam_size": 5,
        "language": language if language and language != "auto" else None,
    }
    
    # initial_promptが指定されている場合は追加
    if initial_prompt and initial_prompt.strip():
        transcribe_options["initial_prompt"] = initial_prompt.strip()
        logger.info(f"{log_prefix}初期プロンプトを使用: {initial_prompt.strip()}")
    
    # 文字起こしの実行
    segments, info = model.transcribe(audio_path, **transcribe_options)
    
    # 結果をデータフレームに変換
    data = []
    for segment in segments:
        data.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text
        })
    
    transcription_time = time.time()
    elapsed = transcription_time - now
    logger.info(f"{log_prefix}文字起こし処理完了: {elapsed:.2f}秒 (検出言語: {info.language if hasattr(info, 'language') else 'N/A'})")
    
    # Pandasデータフレームに変換
    df = pd.DataFrame(data)
    
    logger.info(f"{log_prefix}文字起こし結果を保存: {output_json}")
    # JSONとして保存
    save_dataframe(df, output_json)
    
    save_time = time.time()
    total_time = time.time() - now
    logger.info(f"{log_prefix}文字起こし全工程完了: 合計 {total_time:.2f}秒")
    return df

def main():
    parser = argparse.ArgumentParser(description='音声ファイルの文字起こしを実行する')
    parser.add_argument('audio_path', help='音声ファイルのパス (WAV形式)')
    parser.add_argument('output_json', help='出力JSONファイルのパス')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda', 
                        help='使用するデバイス (CPU または CUDA GPU)')
    parser.add_argument('--language', default='ja', help='音声の言語 (デフォルト: ja)')
    parser.add_argument('--initial-prompt', default='', help='Whisperの初期プロンプト')
    args = parser.parse_args()
    
    transcribe_audio(
        args.audio_path, 
        args.output_json, 
        device=args.device, 
        language=args.language, 
        initial_prompt=args.initial_prompt
    )

if __name__ == "__main__":
    main()