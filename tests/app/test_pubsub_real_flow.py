# tests/app/test_pubsub_real_flow.py
import os
import json
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv
from google.cloud import pubsub_v1

# ───────────────────────────────────────────────────────────
# テスト実行前に .env と .env.develop を読み込んで環境変数をセットアップ
@pytest.fixture(scope="module", autouse=True)
def setup_environment():
    """
    whisper_queue/config/.env および
    whisper_queue/config_develop/.env.develop をロード
    """
    root = Path(__file__).resolve().parents[3]
    # 本番環境
    load_dotenv(root / "whisper_queue" / "config" / ".env", override=True)
    # 開発環境（存在すれば上書き）
    dev_env = root / "whisper_queue" / "config_develop" / ".env.develop"
    if dev_env.exists():
        load_dotenv(dev_env, override=True)

    # 必須環境変数の確認
    for var in ("GCP_PROJECT_ID", "PUBSUB_TOPIC", "PUBSUB_SUBSCRIPTION"):
        assert var in os.environ, f"{var} が設定されていません"
# ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pubsub_clients():
    """
    PublisherClient と SubscriberClient を返すフィクスチャ
    テスト前にサブスクリプションをクリアする
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    topic_id = os.environ["PUBSUB_TOPIC"].split("/")[-1]
    subscription_id = os.environ["PUBSUB_SUBSCRIPTION"].split("/")[-1]

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    
    # テスト環境をクリーンにするため、開始前にメッセージをすべてクリア
    clear_subscription_messages(
        project_id=project_id, 
        subscription_id=subscription_id, 
        subscriber=subscriber
    )

    yield {
        "project_id": project_id,
        "topic_id": topic_id,
        "subscription_id": subscription_id,
        "publisher": publisher,
        "subscriber": subscriber,
    }
    
    # テスト後もクリーンアップ
    clear_subscription_messages(
        project_id=project_id, 
        subscription_id=subscription_id, 
        subscriber=subscriber
    )

def clear_subscription_messages(project_id, subscription_id, subscriber):
    """
    サブスクリプション内の全メッセージをクリアする
    テスト実行前後の初期化に使用
    """
    print(f"サブスクリプション {subscription_id} のメッセージをクリア中...")
    subscription_path = subscriber.subscription_path(project_id, subscription_id)
    
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

def publish_and_receive(clients: dict, message: dict, timeout: int = 30) -> dict | None:
    """
    指定トピックに JSON メッセージを publish → pull して返すヘルパー関数
    ジョブIDを元に特定のメッセージを確実に取得する
    """
    job_id = message.get("job_id")
    # JSON をバイト列にシリアライズ
    data = json.dumps(message).encode("utf-8")
    topic_path = clients["publisher"].topic_path(clients["project_id"], clients["topic_id"])
    
    # Publish - 送信完了を待機
    publish_future = clients["publisher"].publish(topic_path, data=data)
    publish_future.result(timeout=timeout)  # 送信完了を待機
    print(f"メッセージ送信完了: {job_id}")
    
    # 処理完了を待機（少し待つ）
    time.sleep(2)
    
    subscription_path = clients["subscriber"].subscription_path(
        clients["project_id"], clients["subscription_id"]
    )
    
    # 最大3回までリトライ
    for attempt in range(3):
        try:
            # たくさんのメッセージを取得して探す
            response = clients["subscriber"].pull(
                subscription=subscription_path,
                max_messages=10,  # より多く取得
                timeout=timeout,
            )
            
            # 送信したジョブIDと一致するメッセージを探す
            for received in response.received_messages:
                received_data = json.loads(received.message.data.decode("utf-8"))
                if received_data.get("job_id") == job_id:
                    # 該当メッセージを見つけたらACKして返す
                    clients["subscriber"].acknowledge(
                        subscription=subscription_path,
                        ack_ids=[received.ack_id],
                    )
                    print(f"メッセージ受信: {job_id}")
                    return received_data
            
            if response.received_messages:
                print(f"取得したメッセージ({len(response.received_messages)}件)に該当IDが含まれていません。再試行します...")
            else:
                print("メッセージを受信できませんでした。再試行します...")
                
            # ちょっと待ってから再試行
            time.sleep(2)
        except Exception as e:
            print(f"Pub/Sub操作中にエラー発生 (試行 {attempt+1}/3): {e}")
            time.sleep(1)
    
    print(f"メッセージ {job_id} の受信に失敗")
    return None

def compare_pubsub_messages(sent: dict, received: dict) -> bool:
    """
    Pub/Subメッセージを比較する際にタイムスタンプを無視し、
    他のフィールドが一致するかどうかを確認する
    """
    if not received:
        return False
        
    sent_copy = sent.copy()
    received_copy = received.copy()
    
    # タイムスタンプは形式が変わるため無視
    sent_copy.pop("timestamp", None)
    received_copy.pop("timestamp", None)
    
    return sent_copy == received_copy

def test_pubsub_real_flow_new_job(pubsub_clients):
    """
    new_job イベントを送信 → pull して同一の dict が返ってくること
    """
    job_id = f"realflow-test-newjob-{int(time.time())}"  # ユニークなIDを使用
    payload = {
        "event_type": "new_job",
        "job_id": job_id,
        "timestamp": time.time(),
        "error_message": None,
    }

    received = publish_and_receive(pubsub_clients, payload)
    assert received is not None, "メッセージを受信できませんでした"
    assert compare_pubsub_messages(payload, received), f"メッセージ内容が一致しません: {payload} vs {received}"

@pytest.mark.parametrize(
    "event_type,error_message",
    [
        ("job_completed", None),
        ("job_failed", "意図的なテストエラー"),
    ],
)
def test_pubsub_real_flow_completed_and_failed(pubsub_clients, event_type, error_message):
    """
    job_completed / job_failed をそれぞれ送信 → pull して同一の dict が返ってくること
    """
    job_id = f"realflow-test-{event_type}-{int(time.time())}"  # ユニークなIDを使用
    payload = {
        "event_type": event_type,
        "job_id": job_id,
        "timestamp": time.time(),
        "error_message": error_message,
    }

    received = publish_and_receive(pubsub_clients, payload)
    assert received is not None, "メッセージを受信できませんでした"
    assert compare_pubsub_messages(payload, received), f"メッセージ内容が一致しません: {payload} vs {received}"
