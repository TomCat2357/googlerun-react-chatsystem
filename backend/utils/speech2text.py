# utils/speech2text.py
import os
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech as cloud_speech_types
from common_utils.logger import logger
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
# 開発環境の場合はdevelop_env_pathに対応する.envファイルがある
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 環境変数から直接取得
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]


def transcribe_streaming_v2(
    audio_content: bytes, language_codes: list = ["ja-JP"]
) -> list[cloud_speech_types.StreamingRecognizeResponse]:
    """Google Cloud Speech-to-Text APIを使用して、ストリーミングで音声ファイルを文字起こしします。
    引数:
        audio_content (bytes): 文字起こしする音声コンテンツのバイトデータ。
        language_codes (list): 認識に使用する言語コードのリスト。デフォルトは ["ja-JP"]。
    戻り値:
        list[cloud_speech_types.StreamingRecognizeResponse]: 文字起こしされたセグメントを含む認識結果のリスト。
    """
    project_id = GCP_PROJECT_ID  # プロジェクトIDの取得
    client = SpeechClient()

    # API の制限に合わせ、各チャンクサイズを25600バイト（約25KB）に固定
    chunk_length = 25600
    stream = [
        audio_content[start : start + chunk_length]
        for start in range(0, len(audio_content), chunk_length)
    ]
    audio_requests = (
        cloud_speech_types.StreamingRecognizeRequest(audio=audio) for audio in stream
    )

    # RecognitionConfig の設定（単語時刻情報は features 内で指定）
    recognition_config = cloud_speech_types.RecognitionConfig(
        auto_decoding_config=cloud_speech_types.AutoDetectDecodingConfig(),
        language_codes=language_codes,
        model="long",
        features=cloud_speech_types.RecognitionFeatures(enable_word_time_offsets=True),
    )
    streaming_config = cloud_speech_types.StreamingRecognitionConfig(
        config=recognition_config
    )
    config_request = cloud_speech_types.StreamingRecognizeRequest(
        recognizer=f"projects/{project_id}/locations/global/recognizers/_",
        streaming_config=streaming_config,
    )

    def requests(
        config_request: cloud_speech_types.StreamingRecognizeRequest, audio_iter
    ):
        # 最初に設定情報を送信
        yield config_request
        # 続いて音声チャンクを送信
        yield from audio_iter

    # ストリーミング認識を実行
    responses_iterator = client.streaming_recognize(
        requests=requests(config_request, audio_requests)
    )
    responses = []
    for response in responses_iterator:
        responses.append(response)
        for result in response.results:
            logger.debug(f"Transcript: {result.alternatives[0].transcript}")

    return responses