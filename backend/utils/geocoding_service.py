# utils/geocoding_service.py
import base64
import json
from typing import Dict, Any, Optional, Tuple
from google.cloud import secretmanager
from logger import logger
from utils.common import (
    GCP_PROJECT_ID,
    GOOGLE_MAPS_API_KEY_PATH,
    SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY,
)
from utils.maps import get_coordinates, get_address, get_static_map, get_street_view
import os


async def process_single_geocode(
    api_key: str, mode: str, query: str, timestamp: int
) -> Dict[str, Any]:
    """単一のジオコーディングリクエストを処理する"""
    if mode == "address":
        # 住所→緯度経度の変換
        geocode_data = get_coordinates(api_key, query)

        if geocode_data.get("status") == "OK" and geocode_data.get("results"):
            result_data = geocode_data["results"][0]
            location = result_data["geometry"]["location"]
            return {
                "query": query,
                "status": geocode_data.get("status"),
                "formatted_address": result_data.get("formatted_address", ""),
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
                "location_type": result_data["geometry"].get("location_type", ""),
                "place_id": result_data.get("place_id", ""),
                "types": ", ".join(result_data.get("types", [])),
                "error": "",
                "isCached": False,
                "fetchedAt": timestamp,
                "mode": "address",
            }
        else:
            return {
                "query": query,
                "status": geocode_data.get("status", "エラー"),
                "formatted_address": "",
                "latitude": None,
                "longitude": None,
                "location_type": "",
                "place_id": "",
                "types": "",
                "error": geocode_data.get("status", "エラー"),
                "isCached": False,
                "fetchedAt": timestamp,
                "mode": "address",
            }
    else:
        # 緯度経度→住所の変換
        parts = query.replace(" ", "").split(",")

        if len(parts) != 2:
            return {
                "query": query,
                "status": "INVALID_FORMAT",
                "formatted_address": "",
                "latitude": None,
                "longitude": None,
                "location_type": "",
                "place_id": "",
                "types": "",
                "error": "無効な形式",
                "isCached": False,
                "fetchedAt": timestamp,
                "mode": "latlng",
            }
        else:
            try:
                lat = float(parts[0])
                lng = float(parts[1])

                # 緯度経度から標準化されたキャッシュキーを生成
                cache_key = get_latlng_cache_key(lat, lng)

                if lat < -90 or lat > 90 or lng < -180 or lng > 180:
                    return {
                        "query": query,
                        "status": "INVALID_RANGE",
                        "formatted_address": "",
                        "latitude": lat,
                        "longitude": lng,
                        "location_type": "",
                        "place_id": "",
                        "types": "",
                        "error": "範囲外",
                        "isCached": False,
                        "fetchedAt": timestamp,
                        "mode": "latlng",
                    }
                else:
                    geocode_data = get_address(api_key, lat, lng)

                    if geocode_data.get("status") == "OK" and geocode_data.get(
                        "results"
                    ):
                        result_data = geocode_data["results"][0]
                        location = result_data["geometry"]["location"]
                        return {
                            "query": query,
                            "status": geocode_data.get("status"),
                            "formatted_address": result_data.get(
                                "formatted_address", ""
                            ),
                            "latitude": location.get("lat"),
                            "longitude": location.get("lng"),
                            "location_type": result_data["geometry"].get(
                                "location_type", ""
                            ),
                            "place_id": result_data.get("place_id", ""),
                            "types": ", ".join(result_data.get("types", [])),
                            "error": "",
                            "isCached": False,
                            "fetchedAt": timestamp,
                            "mode": "latlng",
                            "cache_key": cache_key,  # キャッシュキーを含める
                        }
                    else:
                        return {
                            "query": query,
                            "status": geocode_data.get("status", "エラー"),
                            "formatted_address": "",
                            "latitude": lat,
                            "longitude": lng,
                            "location_type": "",
                            "place_id": "",
                            "types": "",
                            "error": geocode_data.get("status", "エラー"),
                            "isCached": False,
                            "fetchedAt": timestamp,
                            "mode": "latlng",
                            "cache_key": cache_key,  # キャッシュキーを含める
                        }
            except ValueError:
                return {
                    "query": query,
                    "status": "INVALID_FORMAT",
                    "formatted_address": "",
                    "latitude": None,
                    "longitude": None,
                    "location_type": "",
                    "place_id": "",
                    "types": "",
                    "error": "数値変換エラー",
                    "isCached": False,
                    "fetchedAt": timestamp,
                    "mode": "latlng",
                }


async def process_map_images(
    api_key: str,
    latitude: float,
    longitude: float,
    show_satellite: bool,
    show_street_view: bool,
    satellite_zoom: int,
    street_view_heading: Optional[float],
    street_view_pitch: float,
    street_view_fov: float,
) -> Tuple[Optional[str], Optional[str]]:
    """地図画像を取得する処理"""
    satellite_image = None
    street_view_image = None

    # 衛星画像の取得
    if show_satellite:
        try:
            response = get_static_map(
                api_key,
                latitude,
                longitude,
                zoom=satellite_zoom,
                size=(600, 600),
                map_type="satellite",
            )

            if response.ok:
                img_base64 = base64.b64encode(response.content).decode("utf-8")
                satellite_image = f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            logger.error(f"衛星画像取得エラー: {str(e)}")

    # ストリートビュー画像の取得
    if show_street_view:
        try:
            response = get_street_view(
                api_key,
                latitude,
                longitude,
                size=(600, 600),
                heading=street_view_heading,
                pitch=street_view_pitch,
                fov=street_view_fov,
            )

            if response.ok:
                img_base64 = base64.b64encode(response.content).decode("utf-8")
                street_view_image = f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            logger.error(f"ストリートビュー画像取得エラー: {str(e)}")

    return satellite_image, street_view_image


# 最適化されたジオコード処理関数
async def process_optimized_geocode(
    original_indices,
    query,
    mode,
    api_key,
    timestamp,
    options,
    has_geocode_cache,
    has_satellite_cache,
    has_streetview_cache,
    cached_lat,
    cached_lng,
):
    """
    キャッシュ状態を考慮してジオコーディングを最適化して処理する関数

    Args:
        original_indices (List[int]): 元のリクエスト内でのインデックスのリスト
        query (str): 検索クエリ（住所または緯度経度）
        mode (str): 'address'または'latlng'
        api_key (str): Google Maps API キー
        timestamp (int): 現在のタイムスタンプ
        options (Dict): 表示オプション設定
        has_geocode_cache (bool): 緯度経度のキャッシュがあるか
        has_satellite_cache (bool): 衛星画像のキャッシュがあるか
        has_streetview_cache (bool): ストリートビュー画像のキャッシュがあるか
        cached_lat (float): キャッシュされた緯度
        cached_lng (float): キャッシュされた経度

    Returns:
        List[str]: レスポンスチャンクのリスト
    """
    chunks = []
    show_satellite = options.get("showSatellite", False)
    show_street_view = options.get("showStreetView", False)

    # 緯度経度のキャッシュがある場合は再取得しない
    if has_geocode_cache and cached_lat is not None and cached_lng is not None:
        # キャッシュデータを使用
        if mode == "address":
            result = {
                "query": query,
                "status": "OK",
                "formatted_address": "",  # クライアントから必要に応じて提供
                "latitude": cached_lat,
                "longitude": cached_lng,
                "location_type": "",
                "place_id": "",
                "types": "",
                "isCached": True,
                "fetchedAt": timestamp,
                "mode": mode,
            }
        else:  # latlng モード
            result = {
                "query": query,
                "status": "OK",
                "formatted_address": "",  # クライアントから必要に応じて提供
                "latitude": cached_lat,
                "longitude": cached_lng,
                "location_type": "",
                "place_id": "",
                "types": "",
                "isCached": True,
                "fetchedAt": timestamp,
                "mode": mode,
            }
    else:
        # 通常のジオコーディング処理
        result = await process_single_geocode(api_key, mode, query, timestamp)

    # 各インデックスに対してジオコーディング結果を送信
    for idx in original_indices:
        chunks.append(
            json.dumps(
                {
                    "type": "GEOCODE_RESULT",
                    "payload": {
                        "index": idx,
                        "result": result,
                        "progress": -1,  # 進捗はgenerate_resultsで計算
                    },
                }
            )
            + "\n"
        )

    # 画像取得処理（必要かつ緯度経度が有効な場合のみ）
    if (
        (show_satellite or show_street_view)
        and result["latitude"] is not None
        and result["longitude"] is not None
    ):
        satellite_image = None
        street_view_image = None

        # 衛星画像が必要でキャッシュにない場合
        if show_satellite and not has_satellite_cache:
            # 衛星画像のみ取得
            satellite_image, _ = await process_map_images(
                api_key,
                result["latitude"],
                result["longitude"],
                True,
                False,  # ストリートビューは別に処理
                options.get("satelliteZoom", 18),
                None,
                0,
                90,
            )

        # ストリートビューが必要でキャッシュにない場合
        if show_street_view and not has_streetview_cache:
            # ストリートビュー画像のみ取得
            _, street_view_image = await process_map_images(
                api_key,
                result["latitude"],
                result["longitude"],
                False,  # 衛星画像は別に処理
                True,
                options.get("satelliteZoom", 18),
                options.get("streetViewHeading"),
                options.get("streetViewPitch", 0),
                options.get("streetViewFov", 90),
            )

        # 画像結果がある場合のみ返す
        if satellite_image or street_view_image:
            for idx in original_indices:
                chunks.append(
                    json.dumps(
                        {
                            "type": "IMAGE_RESULT",
                            "payload": {
                                "index": idx,
                                "satelliteImage": satellite_image,
                                "streetViewImage": street_view_image,
                                "progress": -1,
                            },
                        }
                    )
                    + "\n"
                )

    return chunks


# Secret Managerからシークレットを取得するための関数
def access_secret(secret_id, version_id="latest"):
    """
    Secret Managerからシークレットを取得する関数
    グーグルに問い合わせるときのnameは以下の構造になっている。
    projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}
    シークレットマネージャーで作成した場合は、
    projects/{PROJECT_ID}/secrets/{secret_id}
    が得られるが、PROJECT_IDは数値であるが、文字列の方のIDでもOK
    versions情報も下記コードのとおりで支障ない。
    """
    try:
        logger.debug(f"Secret Managerから{secret_id}を取得しています")

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(
            f"Secret Managerからのシークレット取得に失敗: {str(e)}", exc_info=True
        )
        return None


# Google Maps APIキーを取得するための関数
def get_google_maps_api_key():
    """
    環境変数からGoogle Maps APIキーを取得し、なければSecret Managerから取得する
    """

    if GOOGLE_MAPS_API_KEY_PATH and os.path.exists(GOOGLE_MAPS_API_KEY_PATH):
        with open(GOOGLE_MAPS_API_KEY_PATH, "rt") as f:
            logger.debug(
                "環境変数にGoogle Maps APIキーが設定されているため、ファイルから取得します"
            )
            api_key = f.read()
    else:
        logger.debug(
            "環境変数にGoogle Maps APIキーが設定されていないため、Secret Managerから取得します"
        )
        api_key = access_secret(SECRET_MANAGER_ID_FOR_GOOGLE_MAPS_API_KEY)
        if not api_key:
            raise Exception("Google Maps APIキーが見つかりません")
    return api_key


# 緯度経度からキャッシュキーを生成（追加）
def get_latlng_cache_key(lat, lng):
    """
    緯度経度からキャッシュキーを生成する関数
    精度を7桁に制限して緯度経度を文字列に変換する

    Args:
        lat (float): 緯度
        lng (float): 経度

    Returns:
        str: "緯度,経度" 形式のキャッシュキー
    """
    return f"{round(float(lat), 7)},{round(float(lng), 7)}"
