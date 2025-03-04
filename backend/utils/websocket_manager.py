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

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    async def connect(self, websocket: WebSocket, client_id: str):
        # 接続は既にacceptされていると仮定
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket接続: {client_id}")

    async def disconnect(self, client_id: str):
        try:
            if client_id in self.active_connections:
                websocket = self.active_connections[client_id]
                del self.active_connections[client_id]
                try:
                    await websocket.close()
                except Exception as e:
                    logger.warning(f"WebSocket切断中のエラーを無視: {str(e)}")
        except Exception as e:
            logger.error(f"クライアント接続解除中のエラー: {str(e)}", exc_info=True)
            
    async def send_message(self, client_id: str, message: Dict[str, Any]):
        """クライアントにメッセージを送信する"""
        if client_id in self.active_connections:
            try:
                websocket = self.active_connections[client_id]
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
                    logger.debug(f"メッセージを送信しました: {client_id}, type={message.get('type')}")
                    return True
                else:
                    logger.warning(f"WebSocketが接続されていません: {client_id}")
                    self.disconnect(client_id)
                    return False
            except Exception as e:
                logger.error(f"メッセージ送信エラー: {str(e)}")
                self.disconnect(client_id)
                return False
        logger.warning(f"クライアントIDが見つかりません: {client_id}")
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

    async def send_progress(self, client_id: str, progress: int, message: str = ""):
        """進捗状況を送信する"""
        return await self.send_message(client_id, {
            "type": "PROGRESS",
            "payload": {"progress": progress, "message": message}
        })

# WebSocket認証関数
async def verify_token(websocket: WebSocket):
    """
    WebSocketの認証を行う
    """
    try:
        logger.info("WebSocket認証: クライアントからの認証メッセージ待機中")
        # タイムアウト設定の追加
        try:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)  # タイムアウト時間を延長
            logger.info(f"WebSocket認証: メッセージ受信 type={data.get('type')}")
            
            if data.get("type") != "AUTH":
                logger.error(f"WebSocket認証: 不正なメッセージタイプ {data.get('type')}")
                await websocket.close(code=1008, reason="認証が必要です")
                return None

            token = data["payload"].get("token")
            if not token:
                logger.error("WebSocket認証: トークンが見つかりません")
                await websocket.close(code=1008, reason="トークンが見つかりません")
                return None

            # Firebase認証トークンを検証
            try:
                decoded_token = verify_firebase_token(token)
                logger.info(f"WebSocket認証成功: {decoded_token.get('email')}")
                return decoded_token
            except Exception as auth_error:
                logger.error(f"Firebase認証エラー: {str(auth_error)}")
                await websocket.close(code=1008, reason=f"認証エラー: {str(auth_error)}")
                return None
        except asyncio.TimeoutError:
            logger.error("WebSocket認証: タイムアウト")
            await websocket.close(code=1008, reason="認証タイムアウト")
            return None
    except Exception as e:
        logger.error(f"WebSocket認証エラー: {str(e)}")
        try:
            await websocket.close(code=1008, reason=f"認証エラー: {str(e)}")
        except Exception:
            # WebSocketが既に閉じられている場合のエラーを無視
            pass
        return None