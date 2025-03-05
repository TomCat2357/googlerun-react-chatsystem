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
                for file in msg.get("files", []):
                    # ファイルのMIMEタイプとデータを取得
                    mime_type = file.get("mimeType", "")
                    file_data = file.get("content", "")
                    
                    # base64エンコードデータを取得
                    if file_data.startswith("data:") and "," in file_data:
                        _, base64_data = file_data.split(",", 1)
                    else:
                        base64_data = file_data
                    
                    # MIMEタイプに基づいて処理
                    if mime_type.startswith("image/") or mime_type.startswith("audio/"):
                        # 画像ファイルはPart.from_dataとして追加
                        parts.append(Part.from_data(mime_type=mime_type, data=base64_data))

                    else:
                        # テキスト系ファイルは内容をテキストとして追加
                        file_name = file.get("name", "ファイル")
                        file_content = file.get("content", "")
                        parts.append(Part.from_text(f"\n--- {file_name} ---\n{file_content}\n--- ファイル終了 ---\n"))
            
            # ログ出力: 送信するプロンプトの概要
            log_parts = []
            for part in parts:
                if hasattr(part, "text") and part.text:
                    # テキストの場合は先頭20文字程度をログに出力
                    log_parts.append(f"テキスト: {part.text[:20]}{'...' if len(part.text) > 20 else ''}")
                elif hasattr(part, "data") and part.data:
                    # 画像や音声の場合はMIMEタイプのみをログに出力
                    mime_type = getattr(part, "mime_type", "unknown")
                    log_parts.append(f"データ: {mime_type}[サイズ: {len(part.data)//1024}KB]")
            
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
            
            # ログ出力
            log_parts = []
            for part in parts:
                if hasattr(part, "text") and part.text:
                    log_parts.append(f"テキスト: {part.text[:20]}{'...' if len(part.text) > 20 else ''}")
                elif hasattr(part, "data") and part.data:
                    mime_type = getattr(part, "mime_type", "unknown")
                    log_parts.append(f"データ: {mime_type}[サイズ: {len(part.data)//1024}KB]")
            
            logger.info(f"VertexAIへ送信するContent: role={role}, parts={log_parts}")
            
            content_list.append(Content(role=role, parts=parts))
    
    return content_list

def common_message_function(*, model: str, messages: List[Dict[str, Any]], stream: bool = False, **kwargs):
    """
    VertexAI GenerativeModel経由でチャットメッセージを送信し応答を取得する
    """
    try:
        # モデル検証: フロントエンドから送られてきたモデルが環境変数MODELSに含まれているか確認
        allowed_models = os.getenv("MODELS", "").split(",")
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