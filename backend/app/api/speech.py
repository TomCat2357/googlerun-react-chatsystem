# API ルート: speech.py - 音声認識関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any, List
import os, base64, datetime

from app.api.auth import get_current_user
from app.services.speech_service import transcribe_streaming_v2
from common_utils.logger import logger, create_dict_logger, log_request
from common_utils.class_types import SpeechToTextRequest

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# ロギング設定
SPEECH2TEXT_LOG_MAX_LENGTH = int(os.environ["SPEECH2TEXT_LOG_MAX_LENGTH"])
VERIFY_AUTH_LOG_MAX_LENGTH = int(os.environ["VERIFY_AUTH_LOG_MAX_LENGTH"])

router = APIRouter()

@router.post("/speech2text")
async def speech2text(
    request: Request,
    speech_request: SpeechToTextRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    logger.debug("音声認識処理開始")
    try:
        request_info: Dict[str, Any] = await log_request(
            request, current_user, VERIFY_AUTH_LOG_MAX_LENGTH
        )

        audio_data: str = speech_request.audio_data

        if not audio_data:
            logger.error("音声データが見つかりません")
            raise HTTPException(
                status_code=400, detail="音声データが提供されていません"
            )

        # ヘッダー除去（"data:audio/～;base64,..."形式の場合）
        if audio_data.startswith("data:"):
            _, audio_data = audio_data.split(",", 1)

        try:
            audio_bytes: bytes = base64.b64decode(audio_data)
            logger.debug(f"受信した音声サイズ: {len(audio_bytes) / 1024:.2f} KB")
        except Exception as e:
            logger.error(f"音声データのBase64デコードエラー: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"音声データの解析に失敗しました: {str(e)}"
            )

        # 受信したデータが空でないか確認
        if len(audio_bytes) == 0:
            logger.error("音声データが空です")
            raise HTTPException(status_code=400, detail="音声データが空です")

        try:
            # 音声認識処理
            logger.debug("音声認識処理を開始します")
            responses = transcribe_streaming_v2(audio_bytes, language_codes=["ja-JP"])
            logger.debug("音声認識完了")
        except Exception as e:
            logger.error(f"音声認識エラー: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"音声認識エラー: {str(e)}")

        full_transcript: str = ""
        timed_transcription: List[Dict[str, str]] = []

        def format_time(time_obj: datetime.timedelta) -> str:
            seconds: float = time_obj.total_seconds()
            hrs: int = int(seconds // 3600)
            mins: int = int((seconds % 3600) // 60)
            secs: int = int(seconds % 60)
            msecs: int = int(seconds * 1000) % 1000
            return f"{hrs:02d}:{mins:02d}:{secs:02d}.{msecs:03d}"

        for response in responses:
            for result in response.results:
                alternative = result.alternatives[0]
                full_transcript += alternative.transcript + "\n"
                if alternative.words:
                    for w in alternative.words:
                        start_time_str: str = format_time(w.start_offset)
                        end_time_str: str = format_time(w.end_offset)
                        timed_transcription.append(
                            {
                                "start_time": start_time_str,
                                "end_time": end_time_str,
                                "text": w.word,
                            }
                        )
                else:
                    timed_transcription.append(
                        {
                            "start_time": "00:00:00",
                            "end_time": "00:00:00",
                            "text": alternative.transcript,
                        }
                    )

        logger.debug(
            f"文字起こし結果: {len(full_transcript)} 文字, {len(timed_transcription)} セグメント"
        )

        response_data: Dict[str, Any] = {
            "transcription": full_transcript.strip(),
            "timed_transcription": timed_transcription,
        }

        return create_dict_logger(
            response_data,
            meta_info={
                k: request_info[k]
                for k in ("X-Request-Id", "path", "email")
                if k in request_info
            },
            max_length=SPEECH2TEXT_LOG_MAX_LENGTH,
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"音声文字起こしエラー: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))