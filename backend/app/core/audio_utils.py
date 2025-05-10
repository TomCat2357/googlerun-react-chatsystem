"""
音声データに関するユーティリティ関数
"""

import subprocess
from typing import BinaryIO, Optional

def probe_duration(file_obj: BinaryIO) -> float:
    """
    stdin パイプで ffprobe に渡し、ファイルをディスク展開せずに音声長を取得
    
    Args:
        file_obj: バイナリモードで開かれたファイルオブジェクトまたはバイトデータのIO
        
    Returns:
        float: 音声の長さ（秒）
        
    Raises:
        RuntimeError: ffprobeの実行に失敗した場合
    """
    proc = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-i", "pipe:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
        ],
        input=file_obj.read(),  # ストリームでデータを渡す
        capture_output=True,
        check=True,
    )
    
    # ffprobeの出力から秒数を取得
    try:
        return float(proc.stdout.decode('utf-8').strip())
    except (ValueError, UnicodeDecodeError) as e:
        raise RuntimeError(f"ffprobe output processing failed: {e}")
