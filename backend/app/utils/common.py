# app/utils/common.py - 共通ユーティリティ関数

import json
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from firebase_admin import auth
from google.cloud import firestore
from common_utils.logger import logger

# FirestoreのSERVER_TIMESTAMPをJSONに変換するためのカスタムエンコーダー
class FirestoreEncoder(json.JSONEncoder):
    def default(self, obj):
        if obj == firestore.SERVER_TIMESTAMP:
            return {"__special__": "SERVER_TIMESTAMP"}
        return super().default(obj)