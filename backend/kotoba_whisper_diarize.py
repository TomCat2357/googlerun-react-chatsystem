import argparse
import os
import logging
import time
import torch
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import soundfile as sf
import librosa
import torchaudio
from pyannote.audio import Pipeline
from pyannote.core import Segment

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 文末の句読点
PUNC_SENT_END = ['.', '?', '!', '。', '？', '！']

def get_text_with_timestamp(segments):
    """
    セグメントごとのテキストとタイムスタンプを取得
    """
    timestamp_texts = []
    for segment in segments:
        start = segment["start"]
        end = segment["end"]
        text = segment["text"]
        timestamp_texts.append((Segment(start, end), text))
    return timestamp_texts

def add_speaker_info_to_text(timestamp_texts, diarization_result):
    """
    タイムスタンプつきテキストに話者情報を追加
    """
    spk_text = []
    for seg, text in timestamp_texts:
        spk = diarization_result.crop(seg).argmax()
        spk_text.append((seg, spk, text))
    return spk_text

def merge_cache(text_cache):
    """
    テキストキャッシュをマージして一つの文にする
    """
    sentence = ''.join([item[-1] for item in text_cache])
    spk = text_cache[0][1]
    start = text_cache[0][0].start
    end = text_cache[-1][0].end
    return Segment(start, end), spk, sentence

def merge_sentence(spk_text):
    """
    同じ話者の連続した発話をマージする
    """
    merged_spk_text = []
    pre_spk = None
    text_cache = []
    for seg, spk, text in spk_text:
        if spk != pre_spk and pre_spk is not None and len(text_cache) > 0:
            merged_spk_text.append(merge_cache(text_cache))
            text_cache = [(seg, spk, text)]
            pre_spk = spk
        elif text and len(text) > 0 and text[-1] in PUNC_SENT_END:
            text_cache.append((seg, spk, text))
            merged_spk_text.append(merge_cache(text_cache))
            text_cache = []
            pre_spk = spk
        else:
            text_cache.append((seg, spk, text))
            pre_spk = spk
    if len(text_cache) > 0:
        merged_spk_text.append(merge_cache(text_cache))
    return merged_spk_text

def diarize_text(transcribe_result, diarization_result):
    """
    文字起こし結果に話者ダイアライゼーション結果を適用
    """
    timestamp_texts = get_text_with_timestamp(transcribe_result)
    spk_text = add_speaker_info_to_text(timestamp_texts, diarization_result)
    res_processed = merge_sentence(spk_text)
    return res_processed

def write_to_txt(spk_sent, file):
    """
    話者情報付き文字起こし結果をファイルに書き出し
    """
    with open(file, 'w', encoding='utf-8') as fp:
        for seg, spk, sentence in spk_sent:
            line = f'{seg.start:.2f} {seg.end:.2f} {spk} {sentence}\n'
            fp.write(line)

def segment_audio(audio_input, sample_rate, processor, model, device):
    """
    Whisperモデルを使用して音声をセグメント化し文字起こしを行う
    """
    logger.info("音声認識を実行しています...")
    start_time = time.time()
    
    # セグメントに分けて文字起こし
    input_features = processor(audio_input, sampling_rate=sample_rate, return_tensors="pt").input_features.to(device)
    
    # タイムスタンプを有効にして生成
    # 明示的に日本語を指定し、return_timestampsをTrueに設定
    forced_decoder_ids = processor.get_decoder_prompt_ids(language="ja", task="transcribe")
    
    # generate時にreturn_timestampsを有効化
    generated_ids = model.generate(
        input_features,
        forced_decoder_ids=forced_decoder_ids,
        return_timestamps=True
    )
    
    # トークンとタイムスタンプ情報を含む完全な結果を取得
    transcription = processor.batch_decode(generated_ids, output_word_offsets=True)
    
    # セグメント情報を抽出
    segments = []
    
    # transcriptionの形式に基づいてセグメントを抽出
    # transformersのバージョンによって形式が異なる可能性があるためチェック
    if isinstance(transcription, list) and len(transcription) > 0:
        if isinstance(transcription[0], dict) and "chunks" in transcription[0]:
            # 新しいtransformersバージョンの場合
            for chunk in transcription[0]["chunks"]:
                segments.append({
                    "start": chunk.get("timestamp", (0, 0))[0],
                    "end": chunk.get("timestamp", (0, 0))[1],
                    "text": chunk.get("text", "")
                })
        else:
            # 単一の文字列が返された場合は単一セグメントとして扱う
            logger.warning("セグメント情報が得られませんでした。単一セグメントとして処理します。")
            # 特殊トークンを削除するためにskip_special_tokens=Trueを設定
            text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            duration = len(audio_input) / sample_rate
            segments = [{
                "start": 0,
                "end": duration,
                "text": text
            }]
    
    # セグメントが取得できなかった場合のフォールバック
    if not segments:
        logger.warning("セグメント情報が得られませんでした。別の方法で取得を試みます。")
        
        # 別の方法でタイムスタンプを取得
        try:
            result = processor.decode(generated_ids[0], output_offsets=True)
            if hasattr(result, "offset_info") and result.offset_info:
                for info in result.offset_info:
                    segments.append({
                        "start": info.get("start_time", 0),
                        "end": info.get("end_time", 0),
                        "text": info.get("text", "")
                    })
            else:
                # それでも取得できない場合は単一セグメントで
                text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
                duration = len(audio_input) / sample_rate
                segments = [{
                    "start": 0,
                    "end": duration,
                    "text": text
                }]
        except Exception as e:
            logger.error(f"タイムスタンプ抽出に失敗しました: {e}")
            text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            duration = len(audio_input) / sample_rate
            segments = [{
                "start": 0,
                "end": duration,
                "text": text
            }]
    
    logger.info(f"音声認識完了 (所要時間: {time.time() - start_time:.2f}秒)")
    logger.info(f"セグメント数: {len(segments)}")
    
    return segments

def main():
    parser = argparse.ArgumentParser(description="Kotoba-Whisper音声認識と話者ダイアライゼーション")
    parser.add_argument("audio", type=str, help="処理する音声ファイルのパス")
    parser.add_argument("--output_dir", "-o", type=str, default=".", help="出力ディレクトリ")
    parser.add_argument("--model_id", type=str, default="kotoba-tech/kotoba-whisper-v2.0", help="使用するWhisperモデルのID")
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu", help="使用するデバイス")
    parser.add_argument("--diarization", action="store_true", dest="diarization", default=True, help="話者ダイアライゼーションを実行する")
    parser.add_argument("--no-diarization", action="store_false", dest="diarization", help="話者ダイアライゼーションを実行しない")
    parser.add_argument("--output_format", type=str, default="txt", choices=["txt"], help="出力フォーマット")
    parser.add_argument("--hf_token", type=str, default="", help="Hugging Face認証トークン（環境変数HF_TOKENが設定されていない場合に使用）")
    
    args = parser.parse_args()
    
    # 出力ディレクトリの作成
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 開始ログ
    logger.info("処理を開始します")
    logger.info(f"使用デバイス: {args.device}")
    
    # プロセッサとモデルのロード
    logger.info(f"モデル '{args.model_id}' をロードしています...")
    start_time = time.time()
    processor = WhisperProcessor.from_pretrained(args.model_id)
    model = WhisperForConditionalGeneration.from_pretrained(args.model_id).to(args.device)
    # Flash Attention 2を使用（可能な場合）
    if args.device == "cuda":
        model.config.attn_implementation = "flash_attention_2"
    logger.info(f"モデルのロード完了 (所要時間: {time.time() - start_time:.2f}秒)")
    
    # 音声ファイルの読み込みとリサンプリング
    logger.info(f"音声ファイル '{args.audio}' を読み込んでいます...")
    start_time = time.time()
    audio_input, original_sample_rate = sf.read(args.audio)
    logger.info(f"オリジナルのサンプリングレート: {original_sample_rate}Hz")
    
    # リサンプリングを行う
    logger.info("16000Hzにリサンプリングしています...")
    audio_input = librosa.resample(y=audio_input, orig_sr=original_sample_rate, target_sr=16000)
    sample_rate = 16000
    logger.info(f"リサンプリング完了 (所要時間: {time.time() - start_time:.2f}秒)")
    
    # 音声データの前処理と認識
    segments = segment_audio(audio_input, sample_rate, processor, model, args.device)
    
    # ファイル名の取得
    audio_basename = os.path.basename(args.audio)
    
    # 単純な文字起こし結果を保存（特殊トークンなし、整形済み）
    transcription_path = os.path.join(args.output_dir, f"{audio_basename}.txt")
    with open(transcription_path, "w", encoding="utf-8") as file:
        # 全体の文字起こし結果を一行目に書き込む
        full_text = " ".join([segment['text'].strip() for segment in segments])
        # 特殊トークンを削除
        full_text = full_text.replace("<|startoftranscript|>", "").replace("<|ja|>", "").replace("<|transcribe|>", "").strip()
        file.write(f"文字起こし結果: {full_text}\n\n")
        
        # セグメントごとの詳細を書き込む
        file.write("セグメント詳細:\n")
        for i, segment in enumerate(segments, 1):
            # 特殊トークンを削除
            text = segment['text'].replace("<|startoftranscript|>", "").replace("<|ja|>", "").replace("<|transcribe|>", "").strip()
            file.write(f"セグメント {i}: {segment['start']:.2f}秒 - {segment['end']:.2f}秒: {text}\n")
    
    logger.info(f"文字起こし結果を保存しました: {transcription_path}")
    
    # 話者ダイアライゼーションを実行
    if args.diarization:
        logger.info("話者ダイアライゼーションを実行しています...")
        start_time = time.time()
        
        # pyannoteパイプラインのロード
        try:
            # 認証トークンの扱いを改善
            # コマンドライン引数、環境変数の順で確認
            auth_token = args.hf_token or os.environ.get("HF_TOKEN", "")
            
            # トークンがない場合は警告を表示
            if not auth_token:
                logger.warning("Hugging Face認証トークンが設定されていません。")
                logger.warning("以下のいずれかの方法でトークンを設定してください：")
                logger.warning("1. コマンドライン引数: --hf_token YOUR_TOKEN")
                logger.warning("2. 環境変数: export HF_TOKEN='YOUR_TOKEN'")
                logger.warning("3. 話者ダイアライゼーションを無効化: --no-diarization")
                raise ValueError("Hugging Face認証トークンが必要です")
            
            logger.info("Pyannoteの話者ダイアライゼーションモデルをロードしています...")
            
            # モデルが確実にロードされるか確認
            try:
                # 成功したテストコードで使用されていた3.1バージョンのモデルを使用
                diarization_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=auth_token
                )
                
                # CPUを使用するように設定
                diarization_pipeline.to(torch.device(args.device))
                
                if diarization_pipeline is None:
                    raise ValueError("ダイアライゼーションパイプラインのロードに失敗しました")
                
                logger.info("話者ダイアライゼーションを実行中...")
                
                # torchaudioを使用して音声ファイルを読み込む (成功したテストコードの方法)
                waveform, sample_rate = torchaudio.load(args.audio)
                
                # 成功したテストコードの方法で処理を実行
                diarization_result = diarization_pipeline({
                    "waveform": waveform, 
                    "sample_rate": sample_rate
                })
                
                # 文字起こし結果と話者ダイアライゼーション結果を組み合わせる
                logger.info("文字起こし結果と話者ダイアライゼーション結果を統合しています...")
                res = diarize_text(segments, diarization_result)
                
                # 結果を保存
                diarized_path = os.path.join(args.output_dir, f"{audio_basename}_spk.txt")
                write_to_txt(res, diarized_path)
                
                logger.info(f"話者ダイアライゼーション完了 (所要時間: {time.time() - start_time:.2f}秒)")
                logger.info(f"話者ダイアライゼーション結果を保存しました: {diarized_path}")
            except Exception as e:
                logger.error(f"ダイアライゼーションパイプラインのロードエラー: {e}")
                logger.error("モデルがゲートされている可能性があります。https://huggingface.co/pyannote/speaker-diarization-3.1 にアクセスして利用条件に同意してください。")
                raise
        except Exception as e:
            logger.error(f"話者ダイアライゼーションに失敗しました: {e}")
            logger.info("話者ダイアライゼーションなしで処理を続行します")
    
    logger.info("処理が完了しました")

if __name__ == "__main__":
    main()