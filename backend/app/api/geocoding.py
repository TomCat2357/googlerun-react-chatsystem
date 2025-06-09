# API ルート: geocoding.py - ジオコーディング関連のエンドポイント

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, AsyncGenerator
import os, json, asyncio, time

from app.api.auth import get_current_user
from app.services.geocoding_service import get_google_maps_api_key, process_optimized_geocode
from common_utils.logger import logger, wrap_asyncgenerator_logger, log_request
from common_utils.class_types import GeocodingRequest

# 環境変数から設定を読み込み
from dotenv import load_dotenv
load_dotenv("./config/.env")
develop_env_path = "./config_develop/.env.develop"
if os.path.exists(develop_env_path):
    load_dotenv(develop_env_path)

# 設定値の読み込み
GEOCODING_NO_IMAGE_MAX_BATCH_SIZE = int(os.environ["GEOCODING_NO_IMAGE_MAX_BATCH_SIZE"])
GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE = int(os.environ["GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE"])
GEOCODING_BATCH_SIZE = int(os.environ.get("GEOCODING_BATCH_SIZE", "5"))
GEOCODING_LOG_MAX_LENGTH = int(os.environ["GEOCODING_LOG_MAX_LENGTH"])

router = APIRouter()

@router.post("/geocoding")
async def geocoding_endpoint(
    request: Request,
    geocoding_request: GeocodingRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """
    ジオコーディングのための最適化されたRESTfulエンドポイント
    クライアントからキャッシュ情報を受け取り、
    最小限のAPI呼び出しで結果と画像を取得する
    """
    # リクエストの情報を取得
    request_info: Dict[str, Any] = await log_request(request, current_user, GEOCODING_LOG_MAX_LENGTH)
    logger.debug("リクエスト情報: %s", request_info)

    mode: str = geocoding_request.mode
    lines = geocoding_request.lines
    options = geocoding_request.options

    # 上限件数のチェック
    max_batch_size: int = (
        GEOCODING_WITH_IMAGE_MAX_BATCH_SIZE
        if options.get("showSatellite") or options.get("showStreetView")
        else GEOCODING_NO_IMAGE_MAX_BATCH_SIZE
    )

    if len(lines) > max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"入力された件数は{len(lines)}件ですが、1回の送信で取得可能な上限は{max_batch_size}件です。",
        )

    google_maps_api_key: str = get_google_maps_api_key()
    timestamp: int = int(time.time() * 1000)

    # クエリの重複を排除し、元のインデックスを保持
    unique_queries: Dict[str, Dict[str, Any]] = {}
    for idx, line_data in enumerate(lines):
        query: str = line_data.query
        if query not in unique_queries:
            # 最初に出現したクエリの情報をコピー
            unique_queries[query] = {"data": line_data, "indices": [idx]}
        else:
            # 既存のクエリに元のインデックスを追加
            unique_queries[query]["indices"].append(idx)

    logger.debug(f"重複排除後のクエリ数: {len(unique_queries)} (元: {len(lines)})")

    # StreamingResponseを使って結果を非同期的に返す
    @wrap_asyncgenerator_logger(
        meta_info={
            key: request_info[key]
            for key in ("X-Request-Id", "path", "email")
            if key in request_info
        },
        max_length=GEOCODING_LOG_MAX_LENGTH,
    )
    async def generate_results() -> AsyncGenerator[str, None]:
        # 並行処理用のタスクリスト
        tasks: List[asyncio.Task] = []

        # 重複排除したクエリごとにタスクを作成
        for query, query_info in unique_queries.items():
            line_data = query_info["data"]
            original_indices: List[int] = query_info["indices"]

            # 処理タスクを作成
            task: asyncio.Task = process_optimized_geocode(
                original_indices=original_indices,
                query=query,
                mode=mode,
                api_key=google_maps_api_key,
                timestamp=timestamp,
                options=options,
                has_geocode_cache=line_data.has_geocode_cache,
                has_satellite_cache=line_data.has_satellite_cache,
                has_streetview_cache=line_data.has_streetview_cache,
                cached_lat=line_data.latitude,
                cached_lng=line_data.longitude,
            )
            tasks.append(task)

        # 並行実行（ただし、レート制限を考慮して一度に実行するタスク数を制限）
        chunk_size: int = GEOCODING_BATCH_SIZE
        total_chunks: int = (len(tasks) + chunk_size - 1) // chunk_size
        processed_chunks: int = 0

        for i in range(0, len(tasks), chunk_size):
            chunk: List[asyncio.Task] = tasks[i : i + chunk_size]
            chunk_results: List[List[str]] = await asyncio.gather(*chunk)
            processed_chunks += 1

            # 進捗計算
            progress_base: int = int((processed_chunks / total_chunks) * 100)

            # 結果を順番に返す
            for result_chunks in chunk_results:
                for result_chunk in result_chunks:
                    # 進捗情報を埋め込み
                    try:
                        chunk_data: Dict[str, Any] = json.loads(result_chunk.rstrip())
                        if (
                            "payload" in chunk_data
                            and "progress" in chunk_data["payload"]
                        ):
                            if chunk_data["payload"]["progress"] == -1:
                                chunk_data["payload"]["progress"] = progress_base
                            yield json.dumps(chunk_data) + "\n"
                        else:
                            yield result_chunk
                    except:
                        yield result_chunk

            # APIレート制限対策の待機
            if i + chunk_size < len(tasks):
                await asyncio.sleep(1)

        # 全ての処理が完了したことを通知
        yield json.dumps({"type": "COMPLETE", "payload": {}}) + "\n"

    return StreamingResponse(
        generate_results(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Transfer-Encoding": "chunked"},
    )