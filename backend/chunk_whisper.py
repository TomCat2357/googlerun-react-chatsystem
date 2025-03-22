import torch
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import soundfile as sf
import librosa
import logging
import time

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 設定
logger.info("処理を開始します")
model_id = "kotoba-tech/kotoba-whisper-v2.0"
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"使用デバイス: {device}")

# プロセッサとモデルのロード
logger.info(f"モデル '{model_id}' をロードしています...")
start_time = time.time()
processor = WhisperProcessor.from_pretrained(model_id)
model = WhisperForConditionalGeneration.from_pretrained(model_id).to(device)
model.config.attn_implementation = "flash_attention_2"
logger.info(f"モデルのロード完了 (所要時間: {time.time() - start_time:.2f}秒)")

# 音声ファイルの読み込みとリサンプリング
audio_file = "../sound_file/sample1.wav"
logger.info(f"音声ファイル '{audio_file}' を読み込んでいます...")
start_time = time.time()
audio_input, original_sample_rate = sf.read(audio_file)
logger.info(f"オリジナルのサンプリングレート: {original_sample_rate}Hz")

# リサンプリングを行う
logger.info("16000Hzにリサンプリングしています...")
audio_input = librosa.resample(y=audio_input, orig_sr=original_sample_rate, target_sr=16000)
sample_rate = 16000
logger.info(f"リサンプリング完了 (所要時間: {time.time() - start_time:.2f}秒)")
# 音声データの前処理
logger.info("音声データを前処理しています...")
start_time = time.time()

# 音声ファイルを分割して処理する例
def process_in_chunks(audio, chunk_length_sec=10.0, sr=16000):
    logger.info("音声を%d秒のチャンクに分割して処理を開始します", chunk_length_sec)
    chunk_length = int(chunk_length_sec * sr)
    chunks = [audio[i:i+chunk_length] for i in range(0, len(audio), chunk_length)]
    
    logger.info("合計%dチャンクを処理します", len(chunks))
    results = []
    for i, chunk in enumerate(chunks, 1):
        logger.info("チャンク %d/%d を処理中...", i, len(chunks))
        input_features = processor(chunk, sampling_rate=sr, return_tensors="pt").input_features.to(device)
        generated_ids = model.generate(input_features)
        transcription = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        results.append(transcription)
        logger.info("チャンク %d の処理が完了しました", i)
    
    logger.info("全チャンクの処理が完了しました")
    return " ".join(results)
# 分割処理を実行
transcription = process_in_chunks(audio_input)

logger.info("前処理完了 (所要時間: %.2f秒)", time.time() - start_time)

# 結果の表示
logger.info("認識結果: %s", transcription)
logger.info("処理が完了しました")