import argparse
import io
import os
import subprocess
import tempfile
from google.cloud import storage

def is_gcs_path(path):
    """GCSパスかどうかを判定する"""
    return path.startswith("gs://")

def get_gcs_file_bytes(gcs_uri):
    """GCSからファイルをバイトとして取得する"""
    path_without_prefix = gcs_uri[5:]
    bucket_name, blob_path = path_without_prefix.split("/", 1)
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    in_memory_file = io.BytesIO()
    blob.download_to_file(in_memory_file)
    in_memory_file.seek(0)
    
    print(f"Loaded {gcs_uri} into memory")
    return in_memory_file

def get_local_file_bytes(file_path):
    """ローカルファイルをバイトとして取得する"""
    with open(file_path, 'rb') as f:
        data = io.BytesIO(f.read())
    print(f"Loaded {file_path} into memory")
    return data

def get_file_bytes(file_path):
    """ファイルをバイトとして読み込む（GCSパスとローカルパスの両方に対応）"""
    if is_gcs_path(file_path):
        return get_gcs_file_bytes(file_path)
    else:
        return get_local_file_bytes(file_path)

def save_to_gcs(local_path, gcs_uri):
    """ローカルファイルをGCSにアップロードする"""
    path_without_prefix = gcs_uri[5:]
    bucket_name, blob_path = path_without_prefix.split("/", 1)
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    blob.upload_from_filename(local_path)
    print(f"Uploaded {local_path} to {gcs_uri}")

def convert_audio(input_path, output_path, use_gpu=True):
    """音声ファイルをWAV形式に変換する"""
    # 入力ファイルを読み込む
    audio_bytes = get_file_bytes(input_path)
    
    # 一時ファイルに保存
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(input_path)[1])
    temp_input = temp_file.name
    temp_file.close()
    
    with open(temp_input, 'wb') as f:
        f.write(audio_bytes.getvalue())
    
    # 出力先がGCSの場合、ローカルの一時ファイルパスを作成
    local_output = output_path
    if is_gcs_path(output_path):
        local_output = f"temp_output_{os.path.basename(output_path)}"
    
    # FFmpegを使用して変換
    try:
        device_str = "GPU" if use_gpu else "CPU"
        print(f"Converting audio to WAV format using {device_str}...")
        
        # FFmpegコマンド（GPUアクセラレーションはオプショナル）
        ffmpeg_cmd = ['ffmpeg', '-i', temp_input, '-ar', '16000', '-ac', '1']
        
        # GPUを使用する場合は、利用可能なアクセラレーションオプションを追加
        # 注: FFmpegで音声処理にGPUを使うオプションには環境依存があります
        if use_gpu:
            # NVIDIAのGPU支援エンコードが利用可能な場合の例
            # 音声変換では直接GPUを使えない場合も多いため、実際の環境に合わせて調整が必要
            pass
            
        ffmpeg_cmd.append(local_output)
        
        subprocess.run(
            ffmpeg_cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"Conversion successful: {local_output}")
        
        # 出力先がGCSの場合、アップロード
        if is_gcs_path(output_path):
            save_to_gcs(local_output, output_path)
            os.remove(local_output)
            
    except subprocess.CalledProcessError as e:
        print(f"Error converting audio: {e}")
        raise
    except FileNotFoundError:
        print("FFmpeg not found. Please install FFmpeg to enable format conversion.")
        raise
    finally:
        # 一時ファイルを削除
        os.remove(temp_input)

def main():
    parser = argparse.ArgumentParser(description='音声ファイルをWAV形式に変換する')
    parser.add_argument('input_path', help='入力音声ファイルのパス (ローカルまたはGCS)')
    parser.add_argument('output_path', help='出力WAVファイルのパス (ローカルまたはGCS)')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda', 
                       help='使用するデバイス (CPU または CUDA GPU)')
    args = parser.parse_args()
    
    # GPUフラグを設定
    use_gpu = (args.device == 'cuda')
    
    convert_audio(args.input_path, args.output_path, use_gpu=use_gpu)

if __name__ == "__main__":
    main()