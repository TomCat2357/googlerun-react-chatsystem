# tests/app/test_pubsub_integration.py

import os
import time
import json
import pytest
from datetime import datetime, timezone
from google.cloud import pubsub_v1
from tests.app.firebase_t import load_environment, initialize_firestore, clear_collection
from tests.app.test_handle_batch_completion_integration import make_initial_doc

# テスト用コレクション名を環境変数で統一
COLLECTION = os.environ.get("WHISPER_JOBS_COLLECTION", "test_whisper_jobs")


@pytest.fixture(scope="module")
def firestore_client():
    # 環境変数ロード（credentials, PROJECT_ID など）
    load_environment()

    # テスト用コレクション名・メール通知オフを設定
    os.environ["WHISPER_JOBS_COLLECTION"] = COLLECTION
    os.environ["EMAIL_NOTIFICATION"] = "false"

    db = initialize_firestore()
    if not db:
        pytest.skip("Firestore クライアントの初期化に失敗しました")

    # Pub/Subキューをクリア
    clear_pubsub_queue(os.environ["PUBSUB_TOPIC"], os.environ["PUBSUB_SUBSCRIPTION"])
        
    # テスト前後にコレクションをクリア
    clear_collection(db, COLLECTION)
    yield db
    clear_collection(db, COLLECTION)
    
    # テスト後もクリア
    clear_pubsub_queue(os.environ["PUBSUB_TOPIC"], os.environ["PUBSUB_SUBSCRIPTION"])


def clear_pubsub_queue(topic_path, subscription_path):
    """Pub/Subのキューをクリアする"""
    try:
        print(f"Pub/Subキュー {subscription_path} をクリア中...")
        subscriber = pubsub_v1.SubscriberClient()
        
        # 複数回プルして確実にクリアする
        for attempt in range(3):
            try:
                # 一度に最大100件のメッセージを取得
                response = subscriber.pull(
                    subscription=subscription_path,
                    max_messages=100,
                    timeout=10,
                )
                
                if not response.received_messages:
                    print(f"クリア完了: メッセージはありませんでした (試行 {attempt+1}/3)")
                    break
                    
                # 取得したすべてのメッセージをACK
                ack_ids = [msg.ack_id for msg in response.received_messages]
                if ack_ids:
                    subscriber.acknowledge(
                        subscription=subscription_path,
                        ack_ids=ack_ids,
                    )
                    print(f"クリア完了: {len(ack_ids)}件のメッセージを削除しました (試行 {attempt+1}/3)")
                
                # 少し待ってから次の試行
                time.sleep(1)
            except Exception as e:
                print(f"メッセージクリア中にエラー発生 (試行 {attempt+1}/3): {e}")
                time.sleep(1)
                
    except Exception as e:
        print(f"Pub/Subキューのクリア中にエラー: {e}")


def publish_message(topic: str, message: dict):
    """Pub/Sub トピックに JSON メッセージを発行するユーティリティ"""
    publisher = pubsub_v1.PublisherClient()
    # Cloud Function の whisper_queue_pubsub はバイナリを JSON文字列として受け取るのでそのままエンコード
    data = json.dumps(message).encode("utf-8")
    future = publisher.publish(topic, data=data)
    future.result()  # 例外発生ならここで検知


def wait_for_status(db, job_id: str, expected_status: str, timeout: int = 60) -> bool:
    """
    Firestore ドキュメントの status フィールドが期待値になるまで待機。
    タイムアウトまでポーリングし、変化を検知したら True を返す。
    """
    start = time.time()
    coll = db.collection(COLLECTION)
    while time.time() - start < timeout:
        doc = coll.document(job_id).get()
        if doc.exists and doc.to_dict().get("status") == expected_status:
            return True
        # ポーリング間隔を短くする（1秒→0.5秒）
        time.sleep(0.5)
        
    # タイムアウト時に現在の状態をログ出力
    doc = coll.document(job_id).get()
    if doc.exists:
        current_status = doc.to_dict().get("status", "unknown")
        print(f"タイムアウト: job_id={job_id}, 現在のステータス={current_status}, 期待={expected_status}")
    else:
        print(f"タイムアウト: job_id={job_id} のドキュメントが存在しません")
    return False


def test_job_completed_via_pubsub(firestore_client):
    """job_completed イベントを Pub/Sub 経由で送信し、Firestore が completed になることを検証"""
    job_id = "pubsub-int-completed-1"
    # 初期ドキュメント作成
    firestore_client.collection(COLLECTION).document(job_id).set(
        make_initial_doc(job_id)
    )

    # Pub/Sub メッセージ送信
    message = {
        "event_type": "job_completed",
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_message": None,
    }
    publish_message(os.environ["PUBSUB_TOPIC"], message)

    assert wait_for_status(firestore_client, job_id, "completed"), (
        f"{job_id} のステータスが completed に更新されませんでした"
    )


def test_job_failed_via_pubsub(firestore_client):
    """job_failed イベントを Pub/Sub 経由で送信し、Firestore が failed かつ error_message がセットされることを検証"""
    job_id = "pubsub-int-failed-1"
    # 初期ドキュメント作成
    firestore_client.collection(COLLECTION).document(job_id).set(
        make_initial_doc(job_id)
    )

    # Pub/Sub メッセージ送信
    error_text = "テスト故障エラー"
    message = {
        "event_type": "job_failed",
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_message": error_text,
    }
    publish_message(os.environ["PUBSUB_TOPIC"], message)

    # failed になるまで待機
    assert wait_for_status(firestore_client, job_id, "failed"), (
        f"{job_id} のステータスが failed に更新されませんでした"
    )

    # error_message の検証
    rec = firestore_client.collection(COLLECTION).document(job_id).get().to_dict()
    assert error_text in rec.get("error_message", ""), "error_message が正しく設定されていません"
