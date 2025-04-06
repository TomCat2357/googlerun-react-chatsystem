# utils/common.py
import json
from typing import Optional
from fastapi import Request, HTTPException
from firebase_admin import auth
from google.cloud import firestore

# logger.pyから必要な機能をインポート
from common_utils.logger import logger


# FirestoreのSERVER_TIMESTAMPをJSONに変換するためのカスタムエンコーダー
class FirestoreEncoder(json.JSONEncoder):
    def default(self, obj):
        if obj == firestore.SERVER_TIMESTAMP:
            return {"__special__": "SERVER_TIMESTAMP"}
        return super().default(obj)


def get_api_key_for_model(model: str) -> Optional[str]:
    """モデル名からAPIキーを取得する"""
    import os
    import json
    source = model.split("/")[0] if "/" in model else model
    return json.loads(os.environ.get("MODEL_API_KEYS", "{}")).get(source, "")


# 認証ミドルウェア用の依存関係
async def get_current_user(request: Request):
    """
    Extracts and verifies the current user's authentication token from the request headers.

    Validates the Authorization header, verifies the Firebase ID token, and returns the decoded token.
    Raises an HTTPException with a 401 status code if authentication fails.

    Args:
        request (Request): The incoming HTTP request containing authentication headers.

    Returns:
        dict: The decoded Firebase ID token for the authenticated user.

    Raises:
        HTTPException: If no token is present or token verification fails.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("トークンが見つかりません")
        raise HTTPException(status_code=401, detail="認証が必要です")

    token = auth_header.split("Bearer ")[1]
    try:
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        logger.info("認証成功")
        return decoded_token
    except Exception as e:
        logger.error("認証エラー: %s", str(e), exc_info=True)
        raise HTTPException(status_code=401, detail=str(e))