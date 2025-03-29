# %%
import requests
from utils.logger import logger


def get_static_map(
    api_key, latitude, longitude, zoom=18, size=(600, 600), map_type="satellite"
):
    """
    Google Maps Static APIを使用して、指定した地点の静止画像を取得します。

    :param api_key: APIキー
    :param latitude: 緯度
    :param longitude: 経度
    :param zoom: ズームレベル（1: 世界、5: 大陸、10: 都市、15: 通り、20: 建物）
    :param size: 画像サイズ（幅, 高さ）最大640x640ピクセル
    :param map_type: マップタイプ（roadmap, satellite, hybrid, terrain）
    """
    logger.debug(
        "静的地図取得リクエスト開始: 緯度=%s, 経度=%s, ズーム=%s",
        latitude,
        longitude,
        zoom,
    )
    base_url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{latitude},{longitude}",
        "zoom": zoom,
        "size": f"{size[0]}x{size[1]}",
        "maptype": map_type,
        "key": api_key,
    }

    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug("静的地図取得成功。ステータスコード: %s", response.status_code)
    else:
        logger.error("静的地図取得失敗。ステータスコード: %s", response.status_code)
    return response


def get_coordinates(api_key, address):
    """
    住所や建物名などのキーワードから緯度経度を取得します。（ジオコーディング）

    :param api_key: APIキー
    :param address: 住所または建物名などのキーワード
    :return: (緯度, 経度) のタプル。取得できなかった場合は None を返します。
    """
    logger.debug("ジオコーディングリクエスト開始: 住所=%s", address)
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug("ジオコーディング成功。ステータスコード: %s", response.status_code)
    else:
        logger.error("ジオコーディング失敗。ステータスコード: %s", response.status_code)
    data = response.json()
    return data


def get_address(api_key, latitude, longitude):
    """
    緯度経度から住所を取得します。（リバースジオコーディング）

    :param api_key: APIキー
    :param latitude: 緯度
    :param longitude: 経度
    :return: 住所（文字列）。取得できなかった場合は None を返します。
    """
    logger.debug(
        "リバースジオコーディングリクエスト開始: 緯度=%s, 経度=%s", latitude, longitude
    )
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"latlng": f"{latitude},{longitude}", "key": api_key}
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug(
"リバースジオコーディング成功。ステータスコード: %s", response.status_code
        )
    else:
        logger.error(
            "リバースジオコーディング失敗。ステータスコード: %s", response.status_code
        )
    data = response.json()
    return data


def get_street_view(
    api_key, latitude, longitude, size=(600, 600), heading=None, pitch=0, fov=90
):
    """
    Google Maps Street View Static APIを使用して、指定した地点のストリートビューの静止画像を取得します。

    :param api_key: APIキー
    :param latitude: 緯度
    :param longitude: 経度
    :param size: 画像サイズ（幅, 高さ）最大640x640ピクセル
    :param heading: カメラの向き（0〜360度）Noneだと自動
    :param pitch: カメラの上下角度（-90〜90度）
    :param fov: 画像の視野（1〜120度）
    """
    logger.debug(
        "ストリートビュー静止画像取得リクエスト開始: 緯度=%s, 経度=%s, heading=%s, pitch=%s, fov=%s",
        latitude,
        longitude,
        heading,
        pitch,
        fov,
    )
    base_url = "https://maps.googleapis.com/maps/api/streetview"
    params = {
        "size": f"{size[0]}x{size[1]}",
        "location": f"{latitude},{longitude}",
        "pitch": pitch,
        "fov": fov,
        "key": api_key,
    }
    if heading is not None:
        params["heading"] = heading
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.debug(
            "ストリートビュー静止画像取得成功。ステータスコード: %s",
            response.status_code,
        )
    else:
        logger.error(
            "ストリートビュー静止画像取得失敗。ステータスコード: %s",
            response.status_code,
        )
    return response