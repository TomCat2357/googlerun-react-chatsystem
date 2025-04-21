import os
import json
import time
import pytest
from datetime import datetime, timezone
from google.cloud import firestore
from tests.app.firebase_t import load_environment, initialize_firestore, clear_collection
from tests.app.test_handle_batch_completion_integration import make_initial_doc
from whisper_queue.app.main import whisper_queue_pubsub, WhisperPubSubMessageData

# BaseModel は subscription を想定していないため、テスト向けに __getitem__ を追加
WhisperPubSubMessageData.__getitem__ = lambda self, key: getattr(self, key)

# テスト用コレクション名
COLLECTION = os.environ.get("WHISPER_JOBS_COLLECTION", "test_whisper_jobs")


@pytest.fixture(scope="module")
def firestore_client():
    # 環境変数ロード (.env と .env.develop)
    load_environment()
    # テスト設定
    os.environ["WHISPER_JOBS_COLLECTION"] = COLLECTION
    os.environ["EMAIL_NOTIFICATION"] = "false"

    db = initialize_firestore()
    if not db:
        pytest.skip("Firestore クライアントの初期化に失敗しました")

    # テスト前後にコレクションをクリア
    clear_collection(db, COLLECTION)
    yield db
    clear_collection(db, COLLECTION)


def invoke_pubsub_fn(message: dict):
    """
    whisper_queue_pubsub を直接呼び出すユーティリティ。
    cloud_event.data["message"]["data"] に JSON 文字列をセットします。
    """
    # ダミー CloudEvent オブジェクト
    class DummyEvent:
        pass

    evt = DummyEvent()
    evt.data = {"message": {"data": json.dumps(message)}}
    result = whisper_queue_pubsub(evt)
    # 成功時は "OK"
    if isinstance(result, tuple):
        return result[0]
    return result


def wait_for_status(db, job_id: str, expected: str, timeout: int = 10):
    """
    Firestore ドキュメントの status フィールドが期待値になるまでポーリング。
    """
    start = time.time()
    coll = db.collection(COLLECTION)
    while time.time() - start < timeout:
        doc = coll.document(job_id).get()
        if doc.exists and doc.to_dict().get("status") == expected:
            return doc.to_dict()
        time.sleep(0.5)
    return None


def test_new_job_does_not_change_status(firestore_client):
    """
    event_type=new_job ではステータス変更しないことを確認
    """
    job_id = "pubsub-test-newjob"
    firestore_client.collection(COLLECTION).document(job_id).set(
        make_initial_doc(job_id)
    )

    msg = {
        "event_type": "new_job",
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_message": None,
    }
    assert invoke_pubsub_fn(msg) == "OK"

    rec = firestore_client.collection(COLLECTION).document(job_id).get().to_dict()
    assert rec["status"] in ("processing", "queued"), (
        f"new_job でステータスが変わっています: {rec['status']}"
    )


@pytest.mark.parametrize("event_type,expected_status,error_msg", [
    ("job_completed", "completed", None),
    ("job_failed",    "failed",    "故意のエラーテスト"),
])
def test_handle_batch_completion_via_pubsub(
    firestore_client, event_type, expected_status, error_msg
):
    """
    job_completed/job_failed を直接呼び出して、Firestore の状態更新を確認
    """
    job_id = f"pubsub-test-{event_type}"
    data = make_initial_doc(job_id)
    data["status"] = "processing"
    firestore_client.collection(COLLECTION).document(job_id).set(data)

    msg = {
        "event_type": event_type,
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_message": error_msg,
    }
    assert invoke_pubsub_fn(msg) == "OK"

    rec = wait_for_status(firestore_client, job_id, expected_status)
    assert rec is not None, f"{job_id} が {expected_status} になりませんでした"
    if error_msg:
        assert error_msg in rec.get("error_message", ""), "error_message が正しく設定されていません"
    else:
        assert rec.get("error_message", "") in (None, ""), (
            f"完了時の error_message が不正です: {rec.get('error_message')}"
        )
