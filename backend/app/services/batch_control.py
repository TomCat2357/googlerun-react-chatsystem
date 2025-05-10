from datetime import datetime, timedelta
import os
import google.cloud.firestore as firestore

# Firestore クライアント
db = firestore.Client()

# 同時処理上限
MAX_CONCURRENT = int(os.getenv('MAX_CONCURRENT', '5'))

## タイムアウト閾値用環境変数
PROCESS_TIMEOUT_SECONDS = int(os.getenv('PROCESS_TIMEOUT_SECONDS', '300'))
AUDIO_TIMEOUT_MULTIPLIER = float(os.getenv('AUDIO_TIMEOUT_MULTIPLIER', '2.0'))

def clear_stale_processing():
    """
    各ジョブの音声長と固定タイムアウトを比較し、
    processing_started_at からの経過時間が
      max(PROCESS_TIMEOUT_SECONDS, audio_duration_ms/1000 * AUDIO_TIMEOUT_MULTIPLIER)
    を超過したものを failed に移行する
    """
    now = datetime.utcnow()
    for doc in db.collection('whisper_jobs') \
                  .where('status', '==', 'processing') \
                  .stream():
        data = doc.to_dict()
        start: datetime = data.get('processing_started_at')
        duration_ms = data.get('audio_duration_ms')
        if not start:
            continue

        # 閾値秒数を計算
        allowed = PROCESS_TIMEOUT_SECONDS
        if isinstance(duration_ms, (int, float)):
            audio_based = duration_ms / 1000 * AUDIO_TIMEOUT_MULTIPLIER
            allowed = max(allowed, audio_based)

        # タイムアウト判定
        if (now - start).total_seconds() > allowed:
            doc.reference.update({
                'status': 'failed',
                'error': 'processing timeout'
            })

@firestore.transactional
def _atomically_take_job(tx):
    # 1) キューからジョブを1件取得
    queued_docs = list(
        db.collection('whisper_jobs')
          .where('status', '==', 'queued')
          .limit(1)
          .stream(transaction=tx)
    )
    if not queued_docs:
        return None

    # 2) 現在の processing 件数をトランザクション内でカウント
    processing_count = len(list(
        db.collection('whisper_jobs')
          .where('status', '==', 'processing')
          .stream(transaction=tx)
    ))
    if processing_count >= MAX_CONCURRENT:
        return None

    # 3) キュージョブを processing 化（処理開始時刻も記録）
    tx.update(queued_docs[0].reference, {
        'status': 'processing',
        'processing_started_at': firestore.SERVER_TIMESTAMP
    })
    return queued_docs[0]

def trigger_whisper_batch_processing():
    # 事前に一定時間超過の stale ジョブを failed に移行
    clear_stale_processing()

    # 次のキュージョブを取ってバッチ実行
    doc = _atomically_take_job(db.transaction())
    if doc:
        _execute_batch_job_creation(doc.to_dict())