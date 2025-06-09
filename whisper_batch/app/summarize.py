import os
import json
import re
from typing import List, Dict, Any, Optional
from common_utils.logger import logger

def summarize_transcript(
    segments: List[Dict[str, Any]], 
    summary_type: str = "brief",
    max_length: int = 300,
    language: str = "ja"
) -> Dict[str, Any]:
    """
    文字起こし結果を要約
    
    Args:
        segments: 要約対象のセグメントリスト
        summary_type: 要約タイプ ('brief', 'detailed', 'bullet_points')
        max_length: 最大文字数
        language: 言語コード
        
    Returns:
        要約結果を含む辞書
    """
    # セグメントからテキストを結合
    full_text = " ".join([segment.get("text", "") for segment in segments if segment.get("text", "").strip()])
    
    if not full_text.strip():
        logger.warning("要約するテキストがありません")
        return {
            "summary": "",
            "summary_type": summary_type,
            "original_length": 0,
            "summary_length": 0,
            "compression_ratio": 0
        }
    
    # 言語別の文区切りパターン
    sentence_patterns = {
        "ja": r'[。！？]',  # 日本語
        "en": r'[.!?]',        # 英語
        "ko": r'[。！？]',     # 韓国語
        "zh": r'[。！？]'      # 中国語
    }
    
    pattern = sentence_patterns.get(language, r'[.!?。！？]')
    sentences = [s.strip() for s in re.split(pattern, full_text) if s.strip()]
    
    summary = ""
    
    if summary_type == "brief":
        # 簡潔な要約: 最初の数文を取得
        summary_sentences = sentences[:min(3, len(sentences))]
        summary = ("。" if language == "ja" else ". ").join(summary_sentences)
        if language == "ja" and summary and not summary.endswith("。"):
            summary += "。"
        elif language == "en" and summary and not summary.endswith("."):
            summary += "."
            
    elif summary_type == "bullet_points":
        # 箇条書き形式
        key_sentences = sentences[:min(5, len(sentences))]
        bullet_symbol = "\u2022" if language in ["ja", "ko", "zh"] else "\u2022"
        summary = "\n".join([f"{bullet_symbol} {sentence.strip()}" for sentence in key_sentences if sentence.strip()])
        
    elif summary_type == "detailed":
        # 詳細な要約: 重要な文を選択
        important_count = max(1, int(len(sentences) * 0.4))  # 40%を選択
        important_sentences = sentences[:important_count]
        summary = ("。" if language == "ja" else ". ").join(important_sentences)
        if language == "ja" and summary and not summary.endswith("。"):
            summary += "。"
        elif language == "en" and summary and not summary.endswith("."):
            summary += "."
    
    # 最大文字数で制限
    if len(summary) > max_length:
        summary = summary[:max_length].rsplit(' ', 1)[0] + "..."
    
    # 統計情報を計算
    original_length = len(full_text)
    summary_length = len(summary)
    compression_ratio = summary_length / original_length if original_length > 0 else 0
    
    # 話者別統計
    speaker_stats = calculate_speaker_statistics(segments)
    
    result = {
        "summary": summary,
        "summary_type": summary_type,
        "original_length": original_length,
        "summary_length": summary_length,
        "compression_ratio": compression_ratio,
        "total_sentences": len(sentences),
        "speaker_statistics": speaker_stats,
        "language": language
    }
    
    logger.info(f"要約完了: {summary_type}, {original_length}文字 → {summary_length}文字 (圧縮率: {compression_ratio:.2%})")
    
    return result

def calculate_speaker_statistics(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    話者別統計を計算
    
    Args:
        segments: セグメントリスト
        
    Returns:
        話者別統計情報
    """
    speaker_stats = {}
    total_duration = 0
    
    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        text = segment.get("text", "")
        
        duration = end - start
        total_duration += duration
        
        if speaker not in speaker_stats:
            speaker_stats[speaker] = {
                "total_duration": 0,
                "total_words": 0,
                "segment_count": 0,
                "percentage": 0
            }
        
        speaker_stats[speaker]["total_duration"] += duration
        speaker_stats[speaker]["total_words"] += len(text.split())
        speaker_stats[speaker]["segment_count"] += 1
    
    # パーセンテージを計算
    for speaker in speaker_stats:
        if total_duration > 0:
            speaker_stats[speaker]["percentage"] = (speaker_stats[speaker]["total_duration"] / total_duration) * 100
    
    return {
        "speakers": speaker_stats,
        "total_duration": total_duration,
        "unique_speakers": len(speaker_stats)
    }

def extract_key_topics(segments: List[Dict[str, Any]], max_topics: int = 5) -> List[str]:
    """
    キートピックを抽出（簡易版）
    
    Args:
        segments: セグメントリスト
        max_topics: 最大トピック数
        
    Returns:
        キートピックのリスト
    """
    # シンプルなキーワード抽出（実際の産業グレードでは、より高度なNLP技術を使用）
    all_text = " ".join([segment.get("text", "") for segment in segments])
    words = all_text.split()
    
    # 文字数の長い単語を重要語として抽出（簡易版）
    important_words = [word for word in words if len(word) > 3]
    
    # 频度でソート
    from collections import Counter
    word_freq = Counter(important_words)
    
    # 上位単語をキートピックとして返す
    topics = [word for word, freq in word_freq.most_common(max_topics)]
    
    return topics

def save_summary(summary_data: Dict[str, Any], output_path: str):
    """
    要約結果をJSONファイルに保存
    
    Args:
        summary_data: 保存する要約データ
        output_path: 出力ファイルパス
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"要約結果を保存: {output_path}")
        
    except Exception as e:
        logger.error(f"要約結果保存エラー: {str(e)}")
        raise