import os
import json
from typing import List, Dict, Any, Optional
from google.cloud import translate_v2 as translate
from common_utils.logger import logger

# 翻訳クライアント
TRANSLATE_CLIENT = None

def _get_translate_client():
    """翻訳クライアントを取得または初期化"""
    global TRANSLATE_CLIENT
    if TRANSLATE_CLIENT is None:
        try:
            TRANSLATE_CLIENT = translate.Client()
            logger.info("Google Cloud Translate API クライアントを初期化しました")
        except Exception as e:
            logger.error(f"翻訳クライアントの初期化に失敗: {str(e)}")
            TRANSLATE_CLIENT = None
    return TRANSLATE_CLIENT

def translate_segments(
    segments: List[Dict[str, Any]], 
    target_language: str = "en",
    source_language: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    セグメントリストを指定言語に翻訳
    
    Args:
        segments: 翻訳対象のセグメントリスト
        target_language: ターゲット言語コード (例: 'en', 'ja', 'ko')
        source_language: ソース言語コード (自動検出の場合はNone)
        
    Returns:
        翻訳されたセグメントリスト
    """
    client = _get_translate_client()
    if not client:
        logger.error("翻訳クライアントが利用できません")
        return segments
    
    translated_segments = []
    
    for segment in segments:
        original_text = segment.get("text", "")
        
        if not original_text.strip():
            # 空のテキストの場合はそのまま追加
            translated_segments.append(segment)
            continue
            
        try:
            # Google Translate APIで翻訳
            result = client.translate(
                original_text,
                target_language=target_language,
                source_language=source_language
            )
            
            translated_text = result['translatedText']
            detected_language = result.get('detectedSourceLanguage', source_language)
            
            # 翻訳されたセグメントを作成
            translated_segment = segment.copy()
            translated_segment['original_text'] = original_text
            translated_segment['text'] = translated_text
            translated_segment['translated_from'] = detected_language
            translated_segment['translated_to'] = target_language
            translated_segment['translation_confidence'] = result.get('confidence', None)
            
            translated_segments.append(translated_segment)
            
        except Exception as e:
            logger.error(f"セグメント翻訳エラー: {str(e)}")
            # エラーの場合は元のセグメントを使用
            error_segment = segment.copy()
            error_segment['translation_error'] = str(e)
            translated_segments.append(error_segment)
    
    logger.info(f"翻訳完了: {len(segments)}セグメント → {target_language}")
    return translated_segments

def batch_translate_multiple_languages(
    segments: List[Dict[str, Any]], 
    target_languages: List[str]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    複数言語への一括翻訳
    
    Args:
        segments: 翻訳対象のセグメントリスト
        target_languages: ターゲット言語コードのリスト
        
    Returns:
        言語コードをキーとした翻訳結果の辞書
    """
    results = {}
    
    for lang in target_languages:
        logger.info(f"翻訳開始: {lang}")
        translated = translate_segments(segments, target_language=lang)
        results[lang] = translated
        
    return results

def save_translated_segments(segments: List[Dict[str, Any]], output_path: str):
    """
    翻訳されたセグメントをJSONファイルに保存
    
    Args:
        segments: 保存するセグメントリスト
        output_path: 出力ファイルパス
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'segments': segments,
                'total_segments': len(segments),
                'translation_metadata': {
                    'translated_at': str(pd.Timestamp.now()),
                    'source': 'whisper_batch_translate'
                }
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"翻訳結果を保存: {output_path}")
        
    except Exception as e:
        logger.error(f"翻訳結果保存エラー: {str(e)}")
        raise