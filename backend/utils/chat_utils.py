# utils/chat_utils.py
import logging
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Part, Content
from typing import List, Dict, Any, Generator, Optional
from utils.common import (
    logger, 
    MODELS, 
    VERTEX_PROJECT, 
    VERTEX_LOCATION
)

# VertexAIの初期化
def init_vertex_ai():
    try:
        vertexai.init(
            project=VERTEX_PROJECT,
            location=VERTEX_LOCATION
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
    """
    content_list = []
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Contentオブジェクトを作成
        if isinstance(content, str):
            # テキストだけの場合
            parts = [Part.from_text(content)]
            
            # ファイルデータがある場合の処理
            if role == "user" and msg.get("files"):
                logger.info(f"ファイルデータを検出: {len(msg['files'])}個のファイル")
                for file in msg.get("files", []):
                    # ファイルのMIMEタイプとデータを取得
                    mime_type = file.get("mimeType", "")
                    file_data = file.get("content", "")
                    file_name = file.get("name", "不明なファイル")
                    
                    logger.info(f"ファイル処理: {file_name} ({mime_type})")
                    
                    # base64エンコードデータを取得
                    base64_data = ""
                    if file_data.startswith("data:") and "," in file_data:
                        _, base64_data = file_data.split(",", 1)
                    else:
                        base64_data = file_data
                    
                    # MIMEタイプに基づいて処理
                    if mime_type.startswith("image/") or mime_type.startswith("audio/"):
                        # 画像/音声ファイルはPart.from_dataとして追加
                        logger.info(f"{mime_type}ファイルをバイナリデータとして処理: {file_name}")
                        file_part = Part.from_data(mime_type=mime_type, data=base64_data)
                        parts.append(file_part)
                        logger.info(f"{mime_type}ファイルをVertexAIに送信するpartsに追加しました")
                    else:
                        # テキスト系ファイルは内容をテキストとして追加
                        logger.info(f"テキストファイルをテキストデータとして処理: {file_name}")
                        file_part = Part.from_text(f"\n--- {file_name} ---\n{file_data}\n--- ファイル終了 ---\n")
                        parts.append(file_part)
            
            # parts配列の内容をログ出力
            log_parts = []
            for part in parts:
                if hasattr(part, "text") and part.text:
                    # テキストの場合は先頭20文字程度をログに出力
                    log_parts.append(f"テキスト: {part.text[:20]}{'...' if len(part.text) > 20 else ''}")
                elif hasattr(part, "mime_type") and hasattr(part, "data"):
                    # 画像や音声の場合はMIMEタイプとデータサイズを出力
                    mime_type = getattr(part, "mime_type", "unknown")
                    data_size = len(getattr(part, "data", "")) // 1024
                    log_parts.append(f"バイナリ: {mime_type} [サイズ: {data_size}KB]")
            
            logger.info(f"VertexAIへ送信するContent: role={role}, parts={log_parts}")
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
            
            # ログ出力（修正版）
            log_parts = []
            for part in parts:
                if hasattr(part, "text") and part.text:
                    log_parts.append(f"テキスト: {part.text[:20]}{'...' if len(part.text) > 20 else ''}")
                elif hasattr(part, "mime_type") and hasattr(part, "data"):
                    mime_type = getattr(part, "mime_type", "unknown")
                    data_size = len(getattr(part, "data", "")) // 1024
                    log_parts.append(f"バイナリ: {mime_type} [サイズ: {data_size}KB]")
            
            logger.info(f"VertexAIへ送信するContent: role={role}, parts={log_parts}")
            content_list.append(Content(role=role, parts=parts))
    
    return content_list

def common_message_function(*, model: str, messages: List[Dict[str, Any]], stream: bool = False, **kwargs):
    """
    VertexAI GenerativeModel経由でチャットメッセージを送信し応答を取得する
    """
    try:
        # モデル検証: フロントエンドから送られてきたモデルが環境変数MODELSに含まれているか確認
        allowed_models = MODELS.replace('{','').replace('}','').split(",")
        # モデル名がデフォルト値でないか確認（カンマ区切りでオプション:デフォルト値の形式）
        model_options = []
        for model_option in allowed_models:
            if ":" in model_option:
                model_name, is_default = model_option.split(":", 1)
                model_options.append(model_name.strip())
            else:
                model_options.append(model_option.strip())
        
        if model not in model_options:
            logger.error(f"指定されたモデル '{model}' は許可されていません。許可モデル: {model_options}")
            raise ValueError(f"指定されたモデル '{model}' は許可されていません。")
        
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