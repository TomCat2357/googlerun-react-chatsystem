# API ルート: image.py - 画像生成関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import os
from functools import partial

from app.api.auth import get_current_user
from app.services.image_service import generate_image
from common_utils.logger import logger, create_dict_logger, log_request
from common_utils.class_types import GenerateImageRequest

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# ロギング設定
GENERATE_IMAGE_LOG_MAX_LENGTH = int(os.environ["GENERATE_IMAGE_LOG_MAX_LENGTH"])
SENSITIVE_KEYS = os.environ["SENSITIVE_KEYS"].split(",")

router = APIRouter()

# 辞書ロガーのセットアップ
create_dict_logger = partial(create_dict_logger, sensitive_keys=SENSITIVE_KEYS)

@router.post("/generate-image")
async def generate_image_endpoint(
    request: Request,
    image_request: GenerateImageRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    request_info: Dict[str, Any] = await log_request(
        request, current_user, GENERATE_IMAGE_LOG_MAX_LENGTH
    )

    prompt: str = image_request.prompt
    model_name: str = image_request.model_name
    negative_prompt: Optional[str] = image_request.negative_prompt
    number_of_images: Optional[int] = image_request.number_of_images
    seed: Optional[int] = image_request.seed
    aspect_ratio: Optional[str] = image_request.aspect_ratio
    language: Optional[str] = image_request.language
    add_watermark: Optional[bool] = image_request.add_watermark
    safety_filter_level: Optional[str] = image_request.safety_filter_level
    person_generation: Optional[str] = image_request.person_generation

    kwargs: Dict[str, Any] = dict(
        prompt=prompt,
        model_name=model_name,
        negative_prompt=negative_prompt,
        seed=seed,
        number_of_images=number_of_images,
        aspect_ratio=aspect_ratio,
        language=language,
        add_watermark=add_watermark,
        safety_filter_level=safety_filter_level,
        person_generation=person_generation,
    )
    logger.debug(f"generate_image 関数の引数: {kwargs}")

    # 必須パラメータのチェック
    none_parameters: List[str] = [
        key for key, value in kwargs.items() if value is None and key != "seed"
    ]
    if none_parameters:
        return JSONResponse(
            status_code=400, content={"error": f"{none_parameters} is(are) required"}
        )

    try:
        image_list = generate_image(**kwargs)
        if not image_list:
            error_message: str = "画像生成に失敗しました。プロンプトにコンテンツポリシーに違反する内容（人物表現など）が含まれている可能性があります。別の内容を試してください。"
            logger.warning(error_message)
            raise HTTPException(status_code=500, detail=error_message)

        encode_images: List[str] = []
        for img_obj in image_list:
            img_base64: str = img_obj._as_base64_string()
            encode_images.append(img_base64)

        response_data: Dict[str, List[str]] = {"images": encode_images}
        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=GENERATE_IMAGE_LOG_MAX_LENGTH,
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message: str = str(e)
        logger.error(f"画像生成エラー: {error_message}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)