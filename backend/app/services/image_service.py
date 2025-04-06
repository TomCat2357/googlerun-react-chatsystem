# サービス: image_service.py - 画像生成関連のビジネスロジック

import os
from common_utils.logger import logger
from vertexai.preview.vision_models import ImageGenerationModel
import vertexai
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 環境変数から直接取得
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCP_REGION = os.environ["GCP_REGION"]

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
    """
    Imagen生成モデルを使用して画像を生成する

    Args:
        prompt (str): 画像生成のプロンプト
        model_name (str): 使用するモデル名
        negative_prompt (str, optional): ネガティブプロンプト
        number_of_images (int, optional): 生成する画像の数
        seed (int, optional): 乱数シード
        aspect_ratio (str, optional): 画像のアスペクト比
        language (str, optional): プロンプトの言語
        add_watermark (bool, optional): ウォーターマークを追加するか
        safety_filter_level (str, optional): セーフティフィルターレベル
        person_generation (str, optional): 人物生成の許可レベル

    Returns:
        list: 生成された画像オブジェクトのリスト
    """
    # Vertex AI の初期化（認証情報はGOOGLE_APPLICATION_CREDENTIALSで指定されたファイルから取得）
    vertexai.init(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    # Imagen3 モデルのロード
    model = ImageGenerationModel.from_pretrained(model_name)

    # 画像生成の実行
    kwargs = dict(
        prompt=prompt,
        number_of_images=number_of_images,
        negative_prompt=negative_prompt,
        aspect_ratio=aspect_ratio,  # アスペクト比
        language=language,  # プロンプト言語
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