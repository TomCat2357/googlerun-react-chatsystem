import os
import sys
import types
import json
import datetime
from pathlib import Path
from unittest import mock
import pytest
@pytest.fixture(scope="module")
def main_module(tmp_path_factory):
    """Import `whisper_batch.app.main` with Google‑Cloud stubs so that the
    real network APIs are never touched. This fixture also injects minimal
    environment variables so the module can be imported safely.
    """
    # ---- Stub Google Cloud Firestore -------------------------------------------------
    firestore_stub = types.ModuleType("google.cloud.firestore")
    class _FakeBatch:
        def __init__(self):
            self.update = mock.MagicMock()
            self.commit = mock.MagicMock()
    class _FakeFirestoreClient:
        def collection(self, *args, **kwargs):
            # Each collection() call returns a fresh MagicMock so that the caller
            # can configure it as desired in each test.
            return mock.MagicMock()
        def batch(self):
            return _FakeBatch()
        def transaction(self):
            # Transaction objects are plain Mocks – the logic under test calls
            # only `.update()` on them.
            return mock.MagicMock()
    # Simple passthrough decorator used by the production code.
    firestore_stub.Client = _FakeFirestoreClient
    firestore_stub.SERVER_TIMESTAMP = object()
    firestore_stub.transactional = lambda f: f
    sys.modules["google.cloud.firestore"] = firestore_stub
    # Firestore helper (Timestamp type) ------------------------------------------------
    helpers_stub = types.ModuleType("google.cloud.firestore_v1._helpers")
    class _FakeTimestamp(datetime.datetime):
        """Placeholder so that `isinstance(x, Timestamp)` succeeds."""
    helpers_stub.Timestamp = _FakeTimestamp
    sys.modules["google.cloud.firestore_v1._helpers"] = helpers_stub
    # ---- Stub Google Cloud Storage ---------------------------------------------------
    storage_stub = types.ModuleType("google.cloud.storage")
    class _FakeStorageClient:
        def bucket(self, *args, **kwargs):
            bucket = mock.MagicMock()
            bucket.blob.return_value = mock.MagicMock()
            return bucket
    storage_stub.Client = _FakeStorageClient
    sys.modules["google.cloud.storage"] = storage_stub
    # ---- Minimal environment so the main module import does not crash ---------------
    tmp_root = tmp_path_factory.mktemp("tmp_root")
    os.environ.setdefault("WHISPER_JOBS_COLLECTION", "jobs")
    os.environ.setdefault("PROCESS_TIMEOUT_SECONDS", "300")
    os.environ.setdefault("AUDIO_TIMEOUT_MULTIPLIER", "2.0")
    os.environ.setdefault("POLL_INTERVAL_SECONDS", "5")
    os.environ.setdefault("HF_AUTH_TOKEN", "token")
    os.environ.setdefault("DEVICE", "cpu")
    os.environ.setdefault("LOCAL_TMP_DIR", str(tmp_root))
    # Import the target module *after* stubbing.
    import importlib
    main = importlib.import_module("whisper_batch.app.main")
    importlib.reload(main)
    return main
def _build_job_dict(now, status="processing", started_delta_sec=600):
    """Helper to build a Firestore document dict."""
    return {
        "user_id": "u1",
        "user_email": "u1@example.com",
        "filename": "audio.wav",
        "description": "",
        "recording_date": "",
        "gcs_bucket_name": "bucket",
        "audio_size": 1,
        "audio_duration_ms": 60000,  # 60 sec
        "file_hash": "abcd",
        "language": "ja",
        "initial_prompt": "",
        "status": status,
        "created_at": now - datetime.timedelta(seconds=700),
        "updated_at": now - datetime.timedelta(seconds=700),
        "process_started_at": now - datetime.timedelta(seconds=started_delta_sec),
    }
def test_mark_timeout_jobs_marks_failed(main_module):
    fixed_now = datetime.datetime(2025, 5, 5, tzinfo=datetime.timezone.utc)
    # Firestore hierarchy mocks --------------------------------------------------
    batch_mock = mock.MagicMock()
    col_mock = mock.MagicMock()
    db_mock = mock.MagicMock(batch=mock.MagicMock(return_value=batch_mock),
                             collection=mock.MagicMock(return_value=col_mock))
    where_mock = mock.MagicMock()
    col_mock.where.return_value = where_mock
    # Firestore document snapshot stub ------------------------------------------
    snap_mock = mock.MagicMock()
    snap_mock.id = "job1"
    snap_mock.reference = mock.MagicMock()
    snap_mock.to_dict.return_value = _build_job_dict(fixed_now)
    where_mock.stream.return_value = [snap_mock]
    # Patch current time with autospec=True to catch signature issues ------------
    with mock.patch.object(main_module, "_utcnow", autospec=True, return_value=fixed_now):
        main_module._mark_timeout_jobs(db_mock)
    batch_mock.update.assert_called_once_with(snap_mock.reference, mock.ANY)
    batch_mock.commit.assert_called_once()
def test_mark_timeout_jobs_no_update_when_within_timeout(main_module):
    fixed_now = datetime.datetime(2025, 5, 5, tzinfo=datetime.timezone.utc)
    batch_mock = mock.MagicMock()
    col_mock = mock.MagicMock()
    db_mock = mock.MagicMock(batch=mock.MagicMock(return_value=batch_mock),
                             collection=mock.MagicMock(return_value=col_mock))
    where_mock = mock.MagicMock()
    col_mock.where.return_value = where_mock
    snap_mock = mock.MagicMock()
    snap_mock.id = "job1"
    snap_mock.reference = mock.MagicMock()
    # Started only 10 s ago – should *not* timeout.
    snap_mock.to_dict.return_value = _build_job_dict(fixed_now, started_delta_sec=10)
    where_mock.stream.return_value = [snap_mock]
    with mock.patch.object(main_module, "_utcnow", autospec=True, return_value=fixed_now):
        main_module._mark_timeout_jobs(db_mock)
    batch_mock.update.assert_not_called()
    batch_mock.commit.assert_not_called()
def test_pick_next_job_returns_valid_job(main_module):
    tx_mock = mock.MagicMock()
    db_mock = mock.MagicMock(transaction=mock.MagicMock(return_value=tx_mock))
    col_mock = mock.MagicMock()
    db_mock.collection.return_value = col_mock
    where_mock = mock.MagicMock()
    col_mock.where.return_value = where_mock
    order_mock = mock.MagicMock()
    where_mock.order_by.return_value = order_mock
    limit_mock = mock.MagicMock()
    order_mock.limit.return_value = limit_mock
    doc_mock = mock.MagicMock()
    doc_mock.id = "job2"
    doc_mock.reference = mock.MagicMock()
    doc_mock.to_dict.return_value = {
        "user_id": "u1",
        "user_email": "u1@example.com",
        "filename": "audio.wav",
        "description": "",
        "recording_date": "",
        "gcs_bucket_name": "bucket",
        "audio_size": 1,
        "audio_duration_ms": 60000,
        "file_hash": "abcd",
        "language": "ja",
        "initial_prompt": "",
        "status": "queued",
        "created_at": datetime.datetime.utcnow(),
        "updated_at": datetime.datetime.utcnow(),
    }
    limit_mock.stream.return_value = [doc_mock]
    job = main_module._pick_next_job(db_mock)
    assert job is not None and job["job_id"] == "job2"
    tx_mock.update.assert_called_once_with(doc_mock.reference, mock.ANY)
def test_create_single_speaker_json(tmp_path, main_module):
    transcript_data = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.0, "end": 2.0, "text": "world"},
    ]
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps(transcript_data), encoding="utf‑8")
    output_path = tmp_path / "speaker.json"
    main_module.create_single_speaker_json(str(transcript_path), str(output_path))
    with output_path.open(encoding="utf‑8") as fp:
        speaker_data = json.load(fp)
    assert len(speaker_data) == len(transcript_data)
    assert all(item["speaker"] == "SPEAKER_01" for item in speaker_data)
