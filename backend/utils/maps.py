#%%
import requests
from logger import logger

def get_static_map(api_key, latitude, longitude, zoom=18, size=(600, 600), map_type="satellite"):
    """
    Google Maps Static APIを使用して、指定した地点の静止画像を取得します。

    :param api_key: APIキー
    :param latitude: 緯度
    :param longitude: 経度
    :param zoom: ズームレベル（1: 世界、5: 大陸、10: 都市、15: 通り、20: 建物）
    :param size: 画像サイズ（幅, 高さ）最大640x640ピクセル
    :param map_type: マップタイプ（roadmap, satellite, hybrid, terrain）
    """
    logger.info("静的地図取得リクエスト開始: 緯度=%s, 経度=%s, ズーム=%s", latitude, longitude, zoom)
    base_url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{latitude},{longitude}",
        "zoom": zoom,
        "size": f"{size[0]}x{size[1]}",
        "maptype": map_type,
        "key": api_key
    }

    response = requests.get(base_url, params=params)
    if response.ok:
        logger.info("静的地図取得成功。ステータスコード: %s", response.status_code)
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
    logger.info("ジオコーディングリクエスト開始: 住所=%s", address)
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": api_key
    }
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.info("ジオコーディング成功。ステータスコード: %s", response.status_code)
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
    logger.info("リバースジオコーディングリクエスト開始: 緯度=%s, 経度=%s", latitude, longitude)
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{latitude},{longitude}",
        "key": api_key
    }
    response = requests.get(base_url, params=params)
    if response.ok:
        logger.info("リバースジオコーディング成功。ステータスコード: %s", response.status_code)
    else:
        logger.error("リバースジオコーディング失敗。ステータスコード: %s", response.status_code)
    data = response.json()
    return data

#%%
if __name__ == "__main__":
    pass