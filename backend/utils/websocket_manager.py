# utils/websocket_manager.py
import asyncio
import time
import enum
import concurrent.futures
from typing import Dict, Any, List, Optional
from fastapi import WebSocket
from starlette.websockets import WebSocketState
from utils.common import logger, verify_firebase_token

# WebSocketメッセージタイプの定義
class WebSocketMessageType(str, enum.Enum):
    AUTH = "AUTH"
    GEOCODE_REQUEST = "GEOCODE_REQUEST"
    GEOCODE_RESULT = "GEOCODE_RESULT"
    IMAGE_REQUEST = "IMAGE_REQUEST"
    IMAGE_RESULT = "IMAGE_RESULT"
    ERROR = "ERROR"
    COMPLETE = "COMPLETE"


# WebSocketの接続を管理するクラス
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket接続: {client_id}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"WebSocket切断: {client_id}")
            
    async def send_message(self, client_id: str, message: Dict[str, Any]):
        """クライアントにメッセージを送信する"""
        if client_id in self.active_connections:
            try:
                websocket = self.active_connections[client_id]
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
                    return True
                else:
                    self.disconnect(client_id)
                    return False
            except Exception as e:
                logger.error(f"メッセージ送信エラー: {str(e)}")
                self.disconnect(client_id)
                return False
        return False

    def run_in_executor(self, func, *args, **kwargs):
        """別のスレッドで関数を実行する"""
        return self.executor.submit(func, *args, **kwargs)

    async def send_error(self, client_id: str, message: str):
        """エラーメッセージを送信する"""
        return await self.send_message(client_id, {
            "type": WebSocketMessageType.ERROR,
            "payload": {"message": message}
        })

    async def send_complete(self, client_id: str, progress: int = 100):
        """完了メッセージを送信する"""
        return await self.send_message(client_id, {
            "type": WebSocketMessageType.COMPLETE,
            "payload": {"message": "処理が完了しました", "progress": progress}
        })

    async def send_geocode_result(self, client_id: str, index: int, result: Dict[str, Any], progress: int):
        """ジオコーディング結果を送信する"""
        return await self.send_message(client_id, {
            "type": WebSocketMessageType.GEOCODE_RESULT,
            "payload": {"index": index, "result": result, "progress": progress}
        })

    async def send_image_result(self, client_id: str, index: int, 
                               satellite_image: Optional[str], 
                               street_view_image: Optional[str], 
                               progress: int):
        """画像結果を送信する"""
        return await self.send_message(client_id, {
            "type": WebSocketMessageType.IMAGE_RESULT,
            "payload": {
                "index": index,
                "satelliteImage": satellite_image,
                "streetViewImage": street_view_image,
                "progress": progress
            }
        })

# WebSocket認証関数
async def verify_token(websocket: WebSocket):
    """
    WebSocketの認証を行う
    """
    try:
        # クライアントからの最初のメッセージを待機
        data = await websocket.receive_json()
        if data["type"] != "AUTH":
            await websocket.close(code=1008, reason="認証が必要です")
            return None

        token = data["payload"].get("token")
        if not token:
            await websocket.close(code=1008, reason="トークンが見つかりません")
            return None

        # Firebase認証トークンを検証
        decoded_token = verify_firebase_token(token)
        logger.info(f"WebSocket認証成功: {decoded_token.get('email')}")
        return decoded_token
    except Exception as e:
        logger.error(f"WebSocket認証エラー: {str(e)}")
        await websocket.close(code=1008, reason=f"認証エラー: {str(e)}")
        return None