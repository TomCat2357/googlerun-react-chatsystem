"""
音声データに関するユーティリティ関数
"""

import subprocess
import tempfile
import os
from typing import BinaryIO, Optional
from common_utils.logger import logger

def probe_duration(file_path: str) -> float:
    """
    ffprobeを使用して音声ファイルの長さを取得
    
    Args:
        file_path: 音声ファイルのパス
        
    Returns:
        float: 音声の長さ（秒）
        
    Raises:
        RuntimeError: ffprobeの実行に失敗した場合
    """
    try:
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise Exception(
                f"ffprobe failed: {stderr.decode('utf-8', errors='ignore')}"
            )
        return float(stdout.decode('utf-8').strip())
    except FileNotFoundError:
        logger.error("ffprobe not found. Please ensure ffprobe is installed and in your PATH.")
        raise
    except Exception as e:
        logger.error(f"Error probing duration for {file_path}: {e}")
        raise

def convert_audio_to_wav_16k_mono(input_path: str, output_path: str) -> None:
    """
    音声ファイルを16kHzモノラルWAV形式に変換する
    
    Args:
        input_path: 入力音声ファイルのパス
        output_path: 出力WAVファイルのパス
        
    Raises:
        Exception: 変換処理中にエラーが発生した場合
    """
    try:
        # 出力ディレクトリが存在することを確認
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        command = [
            "ffmpeg",
            "-i", input_path,
            "-ar", "16000",  # 16kHzサンプルレート
            "-ac", "1",      # モノラル
            "-y",            # 既存のファイルを上書き
            output_path,
        ]
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            raise Exception(
                f"FFmpeg conversion failed: {stderr.decode('utf-8', errors='ignore')}"
            )
        logger.info(f"Successfully converted {input_path} to {output_path}")
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please ensure FFmpeg is installed and in your PATH.")
        raise
    except Exception as e:
        logger.error(f"Error during audio conversion: {e}")
        raise