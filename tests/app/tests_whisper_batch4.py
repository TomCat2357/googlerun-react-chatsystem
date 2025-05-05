"""
tests/app/tests_whisper_batch4.py

Firestore エミュレータ上で whisper_batch.app.main を直接たたく
統合/単体テスト混在スイート。

実行例:
    $ export FIRESTORE_EMULATOR_HOST=localhost:8900
    $ pytest tests/app/tests_whisper_batch4.py -v
"""

from __future__ import annotations
import datetime as _dt
import importlib
import os
import sys
import types
import uuid
import shutil
from pathlib import Path
from typing import Dict, cast
from unittest import mock

import pytest
from google.cloud import firestore

# ────────────────────────────────────────────────────────────────────────────
# ユーティリティ関数
# ────────────────────────────────────────────────────────────────────────────

def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)

def _rand_suffix() -> str:
    return uuid.uuid4().hex[:8]

def _add_job(
    col_ref: firestore.CollectionReference,
    status: str,
    **extra,
) -> str:
    base: Dict[str, object] = {
        "user_id": "u01",
        "user_email": "tester@example.com",
        "filename": "dummy.wav",
        "description": "",
        "recording_date": "2025-05-05",
        "gcs_bucket_name": "dummy-bucket",
        "audio_size": 1234,
        "audio_duration_ms": 10000,
        "file_hash": "deadbeef",
        "language": "ja",
        "initial_prompt": "",
        "tags": [],
        "num_speakers": None,
        "min_speakers": 1,
        "max_speakers": 1,
    }
    base.update(extra)
    base["status"] = status
    doc = col_ref.document()
    doc.set(base)
    return cast(str, doc.id)

def _count_by_status(
    col_ref: firestore.CollectionReference, status: str
) -> int:
    return len(list(col_ref.where("status", "==", status).stream()))

# ────────────────────────────────────────────────────────────────────────────
# pytest 固定フィクスチャ
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def firestore_client() -> firestore.Client:
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        pytest.skip("エミュレータを起動し、FIRESTORE_EMULATOR_HOST を設定してください")
    return firestore.Client(project=f"test-{_rand_suffix()}")

@pytest.fixture(scope="session")
def collection_name() -> str:
    return f"whisper_jobs_test_{_rand_suffix()}"

@pytest.fixture(scope="session")
def main_module(collection_name: str):
    # 環境変数を設定し、モジュールを再読み込み
    os.environ["WHISPER_JOBS_COLLECTION"] = collection_name
    os.environ["PROCESS_TIMEOUT_SECONDS"] = "5"
    os.environ["AUDIO_TIMEOUT_MULTIPLIER"] = "1.0"
    os.environ["POLL_INTERVAL_SECONDS"] = "1"
    os.environ.setdefault("DEVICE", "cpu")
    os.environ.setdefault("LOCAL_TMP_DIR", "/tmp")

    sys.modules.pop("whisper_batch.app.main", None)
    m = importlib.import_module("whisper_batch.app.main")

    # モジュール内定数を上書き
    m.PROCESS_TIMEOUT_SECONDS = 5
    m.DURATION_TIMEOUT_FACTOR = 1.0
    m.POLL_INTERVAL_SECONDS = 1
    m.COLLECTION = collection_name
    return m

# ────────────────────────────────────────────────────────────────────────────
# 重い依存のスタブ化 (autospec + no-op)
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def _stub_heavy_dependencies(monkeypatch, tmp_path, main_module):
    # GCS クライアントをダミー実装に置換
    storage_stub = types.ModuleType("storage_stub")
    class _DummyBlob:
        download_to_filename = lambda *a, **k: None
        download_as_text     = lambda *a, **k: ""
        upload_from_filename = lambda *a, **k: None
        upload_from_string   = lambda *a, **k: None
    class _DummyBucket:
        def blob(self, *_a, **_kw):
            return _DummyBlob()
    class _DummyStorageClient:
        def bucket(self, *_a, **_kw):
            return _DummyBucket()
    storage_stub.Client = _DummyStorageClient

    monkeypatch.setattr(main_module, "storage", storage_stub, raising=True)

    # Whisper/FFmpeg/pyannote/結合処理をすべて no-op stub に
    import whisper_batch.app.main as _m
    for fn in ("convert_audio", "transcribe_audio", "diarize_audio", "combine_results"):
        orig = getattr(_m, fn)
        monkeypatch.setattr(_m, fn, mock.create_autospec(orig, return_value=None), raising=True)
    # フォーマットチェックも必ず True
    monkeypatch.setattr(
        _m,
        "check_audio_format",
        mock.create_autospec(_m.check_audio_format, return_value=True),
        raising=True,
    )

    # ファイルコピーも no-op にして FileNotFoundError を防止
    monkeypatch.setattr(shutil, "copy2", lambda *a, **k: None, raising=True)

    # 作業ディレクトリを pytest の tmp_path に切り替え
    _m.TMP_ROOT = Path(tmp_path)

# ────────────────────────────────────────────────────────────────────────────
# テストケース
# ────────────────────────────────────────────────────────────────────────────

def test_mark_timeout_jobs_skip_when_no_process_started(
    firestore_client, main_module, collection_name
):
    col = firestore_client.collection(collection_name)
    _add_job(col, "processing")
    before = _count_by_status(col, "failed")
    main_module._mark_timeout_jobs(firestore_client)
    after = _count_by_status(col, "failed")
    assert after == before  # process_started_at がないジョブはスキップ

def test_pick_next_job_returns_none_when_queue_empty(
    firestore_client, main_module, collection_name
):
    col = firestore_client.collection(collection_name)
    assert _count_by_status(col, "queued") == 0
    assert main_module._pick_next_job(firestore_client) is None

def test_process_job_completes_successfully(
    firestore_client, main_module, collection_name, _stub_heavy_dependencies
):
    col = firestore_client.collection(collection_name)
    job_id = _add_job(
        col,
        "processing",
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    job = col.document(job_id).get().to_dict()
    job["job_id"] = job_id

    main_module._process_job(firestore_client, job)
    status = col.document(job_id).get().to_dict()["status"]
    assert status == "completed"

def test_process_job_marks_failed_on_exception(
    firestore_client, main_module, collection_name, _stub_heavy_dependencies
):
    col = firestore_client.collection(collection_name)
    job_id = _add_job(
        col,
        "processing",
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    job = col.document(job_id).get().to_dict()
    job["job_id"] = job_id

    # transcribe_audio に例外を仕込んで失敗パスをテスト
    import whisper_batch.app.main as _m
    _m.transcribe_audio.side_effect = RuntimeError("simulated error")

    main_module._process_job(firestore_client, job)
    status = col.document(job_id).get().to_dict()["status"]
    assert status == "failed"
