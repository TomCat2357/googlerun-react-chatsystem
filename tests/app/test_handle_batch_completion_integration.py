# tests/app/test_handle_batch_completion_integration.py

import os
import pytest
from common_utils.class_types import WhisperPubSubMessageData, WhisperFirestoreData
from whisper_queue.app.main import handle_batch_completion
from tests.app.firebase_t import load_environment, initialize_firestore, clear_collection

# テスト用コレクション名（.env 側のキー名と揃えておく）
COLLECTION = os.environ.get("WHISPER_JOBS_COLLECTION", "test_whisper_jobs")

@pytest.fixture(scope="module")
def firestore_client():
    """
    本番に近い形で Firestore を初期化し、テスト前後にコレクションをクリアするフィクスチャ
    """
    # 環境変数ロード（credentials や PROJECT_ID 等）
    load_environment()  # :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}

    # テスト用にコレクション名とメール通知オフを設定
    os.environ["WHISPER_JOBS_COLLECTION"] = COLLECTION
    os.environ["EMAIL_NOTIFICATION"] = "false"

    db = initialize_firestore()  # :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}
    if not db:
        pytest.skip("Firestore クライアントの初期化に失敗しました")

    # テスト前クリア
    clear_collection(db, COLLECTION)  # :contentReference[oaicite:4]{index=4}&#8203;:contentReference[oaicite:5]{index=5}
    yield db
    # テスト後クリア
    clear_collection(db, COLLECTION)

def make_initial_doc(job_id, user_email="user@example.com"):
    """Firestore に投入する最小限ドキュメントを生成"""
    data = WhisperFirestoreData(
        job_id=job_id,
        user_id="u1",
        user_email=user_email,
        filename="f.mp3",
        description="desc",
        recording_date="2025-04-19",
        gcs_backet_name="bucket",
        audio_file_path="a.mp3",
        transcription_file_path="t.json",
        audio_size=0,
        audio_duration=0,
        file_hash="h",
        status="processing",
        language="ja",
        initial_prompt="",
    ).model_dump()
    return data

class TestHandleBatchCompletionIntegration:
    """handle_batch_completion の E2E に近い統合テスト"""

    def test_completed_updates_firestore(self, firestore_client):
        job_id = "int-job-1"
        # 1) 初期ドキュメントをセット
        firestore_client.collection(COLLECTION).document(job_id).set(
            make_initial_doc(job_id)
        )

        # 2) メッセージを作成
        msg = WhisperPubSubMessageData(
            event_type="job_completed",
            job_id=job_id,
            timestamp="2025-04-19T00:00:00Z",
            error_message=None,
        )

        # 3) 実行
        handle_batch_completion(msg)

        # 4) Firestore から再取得して検証
        rec = firestore_client.collection(COLLECTION).document(job_id).get().to_dict()
        assert rec["status"] == "completed"
        assert "process_ended_at" in rec and "updated_at" in rec
        # 正常系なので error_message は None or 未設定
        assert rec.get("error_message") in (None, "")

    def test_failed_updates_firestore(self, firestore_client):
        job_id = "int-job-2"
        firestore_client.collection(COLLECTION).document(job_id).set(
            make_initial_doc(job_id)
        )

        msg = WhisperPubSubMessageData(
            event_type="job_failed",
            job_id=job_id,
            timestamp="2025-04-19T00:00:00Z",
            error_message="something went wrong",
        )

        handle_batch_completion(msg)

        rec = firestore_client.collection(COLLECTION).document(job_id).get().to_dict()
        assert rec["status"] == "failed"
        assert rec["error_message"] == "something went wrong"
        assert "process_ended_at" in rec and "updated_at" in rec
