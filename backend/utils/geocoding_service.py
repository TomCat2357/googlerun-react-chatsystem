# utils/geocoding_service.py
import base64
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from utils.common import (
    logger, 
    get_google_maps_api_key
)
from utils.maps import get_coordinates, get_address, get_static_map, get_street_view


async def process_single_geocode(
    api_key: str, 
    mode: str, 
    query: str, 
    timestamp: int
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
                "mode": "address"
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
                "mode": "address"
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
                "mode": "latlng"
            }
        else:
            try:
                lat = float(parts[0])
                lng = float(parts[1])
                
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
                        "mode": "latlng"
                    }
                else:
                    geocode_data = get_address(api_key, lat, lng)
                    
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
                            "mode": "latlng"
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
                            "mode": "latlng"
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
                    "mode": "latlng"
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
    street_view_fov: float
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
                map_type="satellite"
            )
            
            if response.ok:
                img_base64 = base64.b64encode(response.content).decode('utf-8')
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
                fov=street_view_fov
            )
            
            if response.ok:
                img_base64 = base64.b64encode(response.content).decode('utf-8')
                street_view_image = f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            logger.error(f"ストリートビュー画像取得エラー: {str(e)}")
    
    return satellite_image, street_view_image