"""
Whisperジョブキューの管理サービス
"""

import os
from fastapi import HTTPException
from google.cloud import firestore
from common_utils.logger import logger

# 環境変数から設定を読み込み
WHISPER_JOBS_COLLECTION = os.environ["WHISPER_JOBS_COLLECTION"]
MAX_PROCESSING_JOBS = int(os.environ.get("MAX_PROCESSING_JOBS", 5))  # デフォルト値は5

# Firestoreクライアント
db = firestore.Client()

def enqueue_job_atomic(job_dict: dict):
    """
    Firestoreトランザクションを使ってジョブを登録し、同時に処理中ジョブ数を原子的に確認する
    
    Args:
        job_dict: 登録するジョブのデータ辞書（"id"キーにジョブIDが含まれている必要がある）
        
    Raises:
        HTTPException: キューが満杯の場合（429）やその他のエラー（500）
    """
    if "id" not in job_dict:
        raise ValueError("ジョブデータに'id'キーが必要です")
    
    job_id = job_dict["id"]
    job_ref = db.collection(WHISPER_JOBS_COLLECTION).document(job_id)
    counter_ref = db.collection("meta").document("counters")
    transaction = db.transaction()
    
    @firestore.transactional
    def txn(tx: firestore.Transaction):
        # カウンタードキュメントを取得（存在しない場合は作成する）
        counter_snap = counter_ref.get(transaction=tx)
        if not counter_snap.exists:
            tx.set(counter_ref, {"processing": 0})
            processing = 0
        else:
            processing = counter_snap.get("processing") or 0
        
        # 処理中ジョブ数の上限チェック
        if processing >= MAX_PROCESSING_JOBS:
            logger.warning(f"処理中ジョブ数が上限（{MAX_PROCESSING_JOBS}）に達しています: 現在{processing}件")
            raise HTTPException(status_code=429, detail="Queue full - too many processing jobs")
        
        # カウンターを増やしてジョブを登録
        tx.update(counter_ref, {"processing": firestore.Increment(1)})
        tx.set(job_ref, job_dict)
        logger.info(f"ジョブ {job_id} を登録しました。処理中ジョブ数: {processing + 1}")
    
    try:
        # トランザクションを実行
        txn(transaction)
    except HTTPException:
        # HTTPExceptionはそのまま再送出
        raise
    except Exception as e:
        logger.error(f"ジョブ登録トランザクションエラー: {str(e)}")
        raise HTTPException(status_code=500, detail=f"ジョブ登録に失敗しました: {str(e)}")

def decrement_processing_counter():
    """
    処理中ジョブカウンターをデクリメントする（ジョブ完了時や失敗時に呼び出す）
    """
    counter_ref = db.collection("meta").document("counters")
    try:
        counter_ref.update({"processing": firestore.Increment(-1)})
        logger.debug("処理中ジョブカウンターをデクリメントしました")
    except Exception as e:
        logger.error(f"カウンターデクリメントエラー: {str(e)}")
