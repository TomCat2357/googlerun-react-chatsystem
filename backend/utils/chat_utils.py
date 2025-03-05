# utils/chat_utils.py
import os
import logging
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Part, Content
from typing import List, Dict, Any, Generator, Optional

logger = logging.getLogger(__name__)

# VertexAIの初期化
def init_vertex_ai():
    try:
        vertexai.init(
            project=os.getenv("VERTEX_PROJECT"),
            location=os.getenv("VERTEX_LOCATION")
        )
        logger.info("VertexAI初期化完了")
    except Exception as e:
        logger.error(f"VertexAI初期化エラー: {str(e)}", exc_info=True)
        raise

# 初期化を1回だけ行う
try:
    init_vertex_ai()
except Exception as e:
    logger.error(f"VertexAI初期化時のエラー: {str(e)}")

def prepare_messages_for_vertex(messages: List[Dict[str, Any]]) -> List[Content]:
    """
    メッセージをVertexAI用のContent形式に変換する
    音声ファイルは最後のものだけ保持する
    """
    content_list = []
    last_audio_file = None
    
    # すべてのメッセージから最後の音声ファイルを見つける
    for msg in messages:
        if msg.get("role") == "user" and "audioFiles" in msg and msg["audioFiles"]:
            last_audio_file = msg["audioFiles"][-1]
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Contentオブジェクトを作成
        if isinstance(content, str):
            # テキストだけの場合
            parts = [Part.from_text(content)]
            
            # この処理は最後のユーザーメッセージにのみ適用
            if role == "user" and last_audio_file and msg == messages[-1]:
                audio_content = last_audio_file.get("content", "")
                if audio_content.startswith("data:"):
                    mime_type, base64_data = audio_content.split(',', 1)
                    mime_type = mime_type.split(':')[1].split(';')[0]
                    parts.append(Part.from_data(mime_type=mime_type, data=base64_data))
            
            content_list.append(Content(role=role, parts=parts))
        elif isinstance(content, list):
            # 複数パーツ（テキスト+画像など）の場合
            parts = []
            for part in content:
                if part.get("type") == "text":
                    parts.append(Part.from_text(part.get("text", "")))
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url", {}).get("url", "")
                    if image_url.startswith("data:"):
                        mime_type, base64_data = image_url.split(',', 1)
                        mime_type = mime_type.split(':')[1].split(';')[0]
                        parts.append(Part.from_data(mime_type=mime_type, data=base64_data))
            
            # 音声ファイルの追加（最後のユーザーメッセージのみ）
            if role == "user" and last_audio_file and msg == messages[-1]:
                audio_content = last_audio_file.get("content", "")
                if audio_content.startswith("data:"):
                    mime_type, base64_data = audio_content.split(',', 1)
                    mime_type = mime_type.split(':')[1].split(';')[0]
                    parts.append(Part.from_data(mime_type=mime_type, data=base64_data))
            
            content_list.append(Content(role=role, parts=parts))
    
    return content_list

def common_message_function(*, model: str, messages: List[Dict[str, Any]], stream: bool = False, **kwargs):
    """
    VertexAI GenerativeModel経由でチャットメッセージを送信し応答を取得する
    """
    try:
        # メッセージをVertexAI用に変換
        content_list = prepare_messages_for_vertex(messages)
        
        # モデルインスタンスの取得
        gen_model = GenerativeModel(model_name=model)
        
        # 生成設定
        generation_config = GenerationConfig(
            temperature=kwargs.get("temperature", 0.2),
            top_p=kwargs.get("top_p", 0.95),
            top_k=kwargs.get("top_k", 40),
            max_output_tokens=kwargs.get("max_tokens", 8192),
            audio_timestamp=kwargs.get("audio_timestamp", True)  # 音声タイムスタンプを有効化
        )
        
        if stream:
            def chat_stream():
                response_stream = gen_model.generate_content(
                    content_list,
                    generation_config=generation_config,
                    stream=True
                )
                
                for response in response_stream:
                    # レスポンスから生成されたテキストを抽出
                    yield response.text if response.text else ""
            
            return chat_stream()
        else:
            response = gen_model.generate_content(
                content_list,
                generation_config=generation_config
            )
            return response.text
    except Exception as e:
        logger.error(f"メッセージ生成エラー: {str(e)}", exc_info=True)
        raise