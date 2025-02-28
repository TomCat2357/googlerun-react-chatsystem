# %%
# from dotenv import load_dotenv
# load_dotenv("../config/.env")
from utils.logger import logger

# from logger import logger

import os
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
        project=os.environ.get("VERTEX_PROJECT"),
        location=os.environ.get("VERTEX_LOCATION"),
    )

    # Imagen3 モデルのロード（モデル名は環境に合わせて変更してください）
    model = ImageGenerationModel.from_pretrained(model_name)

    # 画像生成の実行
    kwarg = dict(
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
        kwarg["seed"] = seed
    images = model.generate_images(*kwarg)
    image_list = images.images
    logger.info("画像の数：%d", len(image_list))
    return image_list  # %%


if __name__ == "__main__":
    # 例：生成したい画像のプロンプト
    prompt_text = "Big ocean and clouds."
    image_list = generate_image(prompt_text, "imagen-3.0-generate-002")
    img_obj = image_list[0]
    img_obj.show()
# %%
