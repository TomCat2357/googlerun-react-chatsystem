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
from common_utils.logger import logger

# グローバルパイプライン - 1度だけ初期化する
_GLOBAL_DIARIZE_PIPELINE = None

def _get_diarize_pipeline(hf_auth_token, device="cuda"):
    """
    グローバルな話者分離パイプラインを取得または初期化する
    
    Args:
        hf_auth_token (str): HuggingFaceの認証トークン
        device (str): 使用するデバイス("cuda"または"cpu")
        
    Returns:
        Pipeline: 初期化済みのpyannoteパイプライン
    """
    global _GLOBAL_DIARIZE_PIPELINE
    
    if _GLOBAL_DIARIZE_PIPELINE is None:
        logger.info(f"初回呼び出し：PyAnnote分離パイプラインをDevice={device}で初期化します")
        start_time = time.time()
        
        # CUDA利用可能かチェック
        if device == "cuda" and torch.cuda.is_available():
            torch_device = torch.device("cuda")
            logger.info("GPUを使用して話者分離を実行します")
        else:
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA要求されましたが利用できません。CPUにフォールバックします。")
            torch_device = torch.device("cpu")
            logger.info("CPUを使用して話者分離を実行します")
        
        # pyannoteのパイプライン設定
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_auth_token
        )
        
        # デバイス設定
        pipeline.to(torch_device)
        
        _GLOBAL_DIARIZE_PIPELINE = pipeline
        
        elapsed = time.time() - start_time
        logger.info(f"話者分離パイプラインの初期化が完了しました（{elapsed:.2f}秒）")
    
    return _GLOBAL_DIARIZE_PIPELINE

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

def diarize_audio(audio_path, output_json, hf_auth_token, min_speakers=None, max_speakers=None, num_speakers=None, device="cuda", job_id=None):
    """音声ファイルの話者分け（ダイアリゼーション）を実行してJSONに保存する"""
    start_time = time.time()
    log_prefix = f"JOB {job_id} " if job_id else ""
    
    try:
        # グローバルパイプラインを取得または初期化
        pipeline = _get_diarize_pipeline(hf_auth_token, device)
        
        # 音声ファイルを読み込む
        logger.info(f"{log_prefix}音声ファイルを読み込み中: {audio_path}")
        load_start_time = time.time()
        waveform, sample_rate = torchaudio.load(audio_path)
        load_time = time.time() - load_start_time
        logger.info(f"{log_prefix}音声読み込み完了: {load_time:.2f}秒")
        
        # ダイアリゼーションパラメータの設定
        diarization_params = {}
        
        if num_speakers is not None:
            diarization_params["num_speakers"] = num_speakers
            logger.info(f"{log_prefix}話者数を固定: {num_speakers}人")
        else:
            if min_speakers is not None:
                diarization_params["min_speakers"] = min_speakers
            if max_speakers is not None:
                diarization_params["max_speakers"] = max_speakers
            logger.info(f"{log_prefix}話者数範囲: {min_speakers}〜{max_speakers}人")
        
        # 話者分け（ダイアリゼーション）の実行
        logger.info(f"{log_prefix}話者分離処理を実行中...")
        diarize_start_time = time.time()
        diarization = pipeline(
            {"waveform": waveform, "sample_rate": sample_rate},
            **diarization_params
        )
        diarize_time = time.time() - diarize_start_time
        logger.info(f"{log_prefix}話者分離処理完了: {diarize_time:.2f}秒")
        
        # 結果をデータフレームに変換
        logger.info(f"{log_prefix}話者分離結果を処理中...")
        process_start_time = time.time()
        data = []
        unique_speakers = set()
        for segment, _, speaker in diarization.itertracks(yield_label=True):
            data.append({
                "start": segment.start,
                "end": segment.end,
                "speaker": speaker
            })
            unique_speakers.add(speaker)
        speaker_count = len(unique_speakers)
        
        # Pandasデータフレームに変換
        df = pd.DataFrame(data)
        process_time = time.time() - process_start_time
        logger.info(f"{log_prefix}話者分離結果: {speaker_count}人の話者を検出")
        
        # JSONとして保存
        logger.info(f"{log_prefix}話者分離結果を保存: {output_json}")
        save_start_time = time.time()
        save_dataframe(df, output_json)
        save_time = time.time() - save_start_time
        
        total_time = time.time() - start_time
        logger.info(f"{log_prefix}話者分離全工程完了: 合計 {total_time:.2f}秒")
        
        # 時間の内訳をログに記録
        logger.info(f"{log_prefix}話者分離時間内訳: 音声読込={load_time:.2f}秒, 分離処理={diarize_time:.2f}秒, 結果処理={process_time:.2f}秒, 保存={save_time:.2f}秒")
        
        return df
        
    except Exception as e:
        error_time = time.time() - start_time
        logger.error(f"{log_prefix}話者分離処理でエラー発生 ({error_time:.2f}秒経過): {e}")
        raise Exception(f"話者分離処理でエラー: {e}")

def main():
    parser = argparse.ArgumentParser(description='音声ファイルの話者分離を実行する')
    parser.add_argument('audio_path', help='音声ファイルのパス (WAV形式)')
    parser.add_argument('output_json', help='出力JSONファイルのパス')
    parser.add_argument('hf_auth_token', help='HuggingFace認証トークン (必須)')
    parser.add_argument('--min-speakers', type=int, help='最小話者数')
    parser.add_argument('--max-speakers', type=int, help='最大話者数')
    parser.add_argument('--num-speakers', type=int, help='固定話者数（min/maxよりも優先）')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda', 
                       help='使用するデバイス (CPU または CUDA GPU)')
    args = parser.parse_args()
    
    
    diarize_audio(
        args.audio_path, 
        args.output_json,
        args.hf_auth_token,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        num_speakers=args.num_speakers,
        device=args.device
    )

if __name__ == "__main__":
    main()