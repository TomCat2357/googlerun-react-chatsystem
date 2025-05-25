# API ルート: chat.py - チャット関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Union, AsyncGenerator
import os

from app.api.auth import get_current_user
from app.services.chat_service import get_api_key_for_model, common_message_function
from common_utils.logger import logger, wrap_asyncgenerator_logger, log_request
from common_utils.class_types import ChatRequest

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# ロギング設定
CHAT_LOG_MAX_LENGTH = int(os.environ["CHAT_LOG_MAX_LENGTH"])

router = APIRouter()

@router.post("/chat")
async def chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    logger.debug("チャットリクエストを処理中")
    try:
        request_info: Dict[str, Any] = await log_request(request, current_user, CHAT_LOG_MAX_LENGTH)
        logger.debug("リクエスト情報: %s", request_info)

        messages: List[Dict[str, Any]] = chat_request.messages
        model: str = chat_request.model
        logger.debug(f"モデル: {model}")

        if model is None:
            raise HTTPException(
                status_code=400, detail="モデル情報が提供されていません"
            )

        model_api_key: str = get_api_key_for_model(model)

        # メッセージ変換処理のログ出力を追加
        transformed_messages: List[Dict[str, Any]] = []
        for msg in messages:
            # ユーザーメッセージに添付ファイルがある場合の処理
            if msg.get("role") == "user":
                # ファイルデータの処理とログ出力
                if "files" in msg and msg["files"]:
                    file_types: List[str] = []
                    for file in msg["files"]:
                        mime_type: str = file.get("mimeType", "")
                        name: str = file.get("name", "")
                        file_types.append(f"{name} ({mime_type})")
                    logger.debug(f"添付ファイル: {', '.join(file_types)}")

                # メッセージをそのまま追加（prepare_message_for_aiは使わない）
                transformed_messages.append(msg)
            else:
                # システムメッセージまたはアシスタントメッセージはそのまま
                transformed_messages.append(msg)
        logger.debug(f"選択されたモデル: {model}")

        # プロンプト内容の概要をログに出力
        for i, msg in enumerate(transformed_messages):
            role: str = msg.get("role", "unknown")
            content: Union[str, List[Dict[str, Any]]] = msg.get("content", "")

            if isinstance(content, str):
                content_preview: str = content[:50] + "..." if len(content) > 50 else content
                logger.debug(f"メッセージ[{i}]: role={role}, content={content_preview}")
            elif isinstance(content, list):
                parts_info: List[str] = []
                for part in content:
                    if part.get("type") == "text":
                        text: str = (
                            part.get("text", "")[:20] + "..."
                            if len(part.get("text", "")) > 20
                            else part.get("text", "")
                        )
                        parts_info.append(f"text: {text}")
                    elif part.get("type") == "image_url":
                        parts_info.append("image")
                logger.debug(f"メッセージ[{i}]: role={role}, parts={parts_info}")

        # ストリーミングレスポンスの作成
        @wrap_asyncgenerator_logger(
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=CHAT_LOG_MAX_LENGTH,
        )
        async def generate_stream() -> AsyncGenerator[str, None]:
            for chunk in common_message_function(
                model=model,
                stream=True,
                messages=transformed_messages,
                api_key=model_api_key,
            ):
                yield chunk

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Transfer-Encoding": "chunked"},
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error("チャットエラー: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))