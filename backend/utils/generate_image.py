# utils/generate_image.py
from utils.common import (
    GCP_PROJECT_ID,
    GCP_REGION
)
from logger import logger

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel


def generate_image(
    prompt: str,
    model_name: str,
    negative_prompt: str = "",
    number_of_images=1,
    seed=None,
    aspect_ratio="1:1",
    language="auto",
    add_watermark=False,
    safety_filter_level="block_medium_and_above",
    person_generation="allow_adult",
):
    # Vertex AI の初期化（認証情報はGOOGLE_APPLICATION_CREDENTIALSで指定されたファイルから取得）
    vertexai.init(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    # Imagen3 モデルのロード（モデル名は環境に合わせて変更してください）
    model = ImageGenerationModel.from_pretrained(model_name)

    # 画像生成の実行
    kwargs = dict(
        prompt=prompt,
        number_of_images=number_of_images,
        negative_prompt=negative_prompt,
        aspect_ratio=aspect_ratio,  # アスペクト比（例：正方形）
        language=language,  # プロンプト言語（日本語）
        add_watermark=add_watermark,
        safety_filter_level=safety_filter_level,
        person_generation=person_generation,
    )
    if seed is not None:
        kwargs["seed"] = seed
    images = model.generate_images(**kwargs)
    image_list = images.images
    logger.debug("画像の数：%d", len(image_list))
    return image_list