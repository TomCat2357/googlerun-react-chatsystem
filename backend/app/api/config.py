# API ルート: config.py - 設定関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any
import os
from functools import partial

from app.api.auth import get_current_user
from common_utils.logger import logger, create_dict_logger, log_request

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 設定値の読み込み
MAX_IMAGES = int(os.environ["MAX_IMAGES"])
MAX_AUDIO_FILES = int(os.environ["MAX_AUDIO_FILES"])
MAX_TEXT_FILES = int(os.environ["MAX_TEXT_FILES"])
MAX_LONG_EDGE = int(os.environ["MAX_LONG_EDGE"])
MAX_IMAGE_SIZE = int(os.environ["MAX_IMAGE_SIZE"])
GOOGLE_MAPS_API_CACHE_TTL = int(os.environ["GOOGLE_MAPS_API_CACHE_TTL"])
GEOCODING_NO_IMAGE_MAX_BATCH_SIZE = int(os.environ["GEOCODING_NO_IMAGE_MAX_BATCH_SIZE"])
GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE = int(os.environ["GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE"])
SPEECH_MAX_SECONDS = int(os.environ["SPEECH_MAX_SECONDS"])
MODELS = os.environ["MODELS"]
IMAGEN_MODELS = os.environ["IMAGEN_MODELS"]
IMAGEN_NUMBER_OF_IMAGES = os.environ["IMAGEN_NUMBER_OF_IMAGES"]
IMAGEN_ASPECT_RATIOS = os.environ["IMAGEN_ASPECT_RATIOS"]
IMAGEN_LANGUAGES = os.environ["IMAGEN_LANGUAGES"]
IMAGEN_ADD_WATERMARK = os.environ["IMAGEN_ADD_WATERMARK"]
IMAGEN_SAFETY_FILTER_LEVELS = os.environ["IMAGEN_SAFETY_FILTER_LEVELS"]
IMAGEN_PERSON_GENERATIONS = os.environ["IMAGEN_PERSON_GENERATIONS"]
WHISPER_MAX_SECONDS = int(os.environ["WHISPER_MAX_SECONDS"])

# ロギング設定
CONFIG_LOG_MAX_LENGTH = int(os.environ["CONFIG_LOG_MAX_LENGTH"])
SENSITIVE_KEYS = os.environ["SENSITIVE_KEYS"].split(",")

router = APIRouter()

# 辞書ロガーのセットアップ
create_dict_logger = partial(create_dict_logger, sensitive_keys=SENSITIVE_KEYS)

@router.get("/config")
async def get_config(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, CONFIG_LOG_MAX_LENGTH
        )
        logger.debug("リクエスト情報: %s", request_info)

        config_values: Dict[str, Any] = {
            "MAX_IMAGES": MAX_IMAGES,
            "MAX_AUDIO_FILES": MAX_AUDIO_FILES,
            "MAX_TEXT_FILES": MAX_TEXT_FILES,
            "MAX_LONG_EDGE": MAX_LONG_EDGE,
            "MAX_IMAGE_SIZE": MAX_IMAGE_SIZE,
            "GOOGLE_MAPS_API_CACHE_TTL": GOOGLE_MAPS_API_CACHE_TTL,
            "GEOCODING_NO_IMAGE_MAX_BATCH_SIZE": GEOCODING_NO_IMAGE_MAX_BATCH_SIZE,
            "GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE": GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE,
            "SPEECH_MAX_SECONDS": SPEECH_MAX_SECONDS,
            "MODELS": MODELS,
            "IMAGEN_MODELS": IMAGEN_MODELS,
            "IMAGEN_NUMBER_OF_IMAGES": IMAGEN_NUMBER_OF_IMAGES,
            "IMAGEN_ASPECT_RATIOS": IMAGEN_ASPECT_RATIOS,
            "IMAGEN_LANGUAGES": IMAGEN_LANGUAGES,
            "IMAGEN_ADD_WATERMARK": IMAGEN_ADD_WATERMARK,
            "IMAGEN_SAFETY_FILTER_LEVELS": IMAGEN_SAFETY_FILTER_LEVELS,
            "IMAGEN_PERSON_GENERATIONS": IMAGEN_PERSON_GENERATIONS,
            "WHISPER_MAX_SECONDS" : WHISPER_MAX_SECONDS,
        }
        logger.debug("Config取得成功")
        return create_dict_logger(
            config_values,
            meta_info={
                key: request_info[key]
                for key in ("X-Request-Id", "path", "email")
                if key in request_info
            },
            max_length=CONFIG_LOG_MAX_LENGTH,
        )
    except Exception as e:
        logger.error("Config取得エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))