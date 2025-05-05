"""
tests/app/tests_whisper_batch5.py

追加カバレッジ
--------------------------------------------------
1) 長時間音声での DURATION_TIMEOUT_FACTOR 判定
2) check_audio_format が False の場合に convert_audio が呼ばれること
3) データモデル検証失敗時に failed へ遷移すること
"""

from __future__ import annotations

import datetime as _dt
import importlib
import os
import sys
import types
import uuid
from pathlib import Path
from typing import Dict
from unittest import mock

import pytest
from google.cloud import firestore

# ── ユーティリティ ──────────────────────────────────────────────

def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)

def _rand_suffix() -> str:
    return uuid.uuid4().hex[:8]

_BASE_FIELDS: Dict[str, object] = {
    "user_id": "u01",
    "user_email": "tester@example.com",
    "description": "",
    "recording_date": "2025-05-05",
    "gcs_bucket_name": "dummy-bucket",
    "audio_size": 1234,
    "audio_duration_ms": 1_000,
    "file_hash": "deadbeef",
    "language": "ja",
    "initial_prompt": "",
    "tags": [],
    "num_speakers": None,
    "min_speakers": 1,
    "max_speakers": 1,
}

def _add_job(col: firestore.CollectionReference, status: str, **extra) -> str:  # type: ignore[valid-type]
    data = {**_BASE_FIELDS, **extra, "status": status}
    doc = col.document()
    doc.set(data)
    return str(doc.id)

def _count(col: firestore.CollectionReference, status: str) -> int:  # type: ignore[valid-type]
    return len(list(col.where("status", "==", status).stream()))

# ── pytest 固定フィクスチャ ────────────────────────────────────

@pytest.fixture(scope="session")
def firestore_client() -> firestore.Client:  # type: ignore[valid-type]
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        pytest.skip("FIRESTORE_EMULATOR_HOST が未設定のため Firestore テストをスキップ")
    return firestore.Client(project=f"test-{_rand_suffix()}")

@pytest.fixture(scope="session")
def collection_name() -> str:
    return f"whisper_jobs_test_{_rand_suffix()}"

@pytest.fixture(scope="session")
def main_module(collection_name: str):
    # 環境変数・モジュール再ロード
    os.environ["WHISPER_JOBS_COLLECTION"] = collection_name
    os.environ["PROCESS_TIMEOUT_SECONDS"] = "5"
    os.environ["AUDIO_TIMEOUT_MULTIPLIER"] = "1.0"
    os.environ["POLL_INTERVAL_SECONDS"] = "1"
    os.environ.setdefault("DEVICE", "cpu")
    os.environ.setdefault("LOCAL_TMP_DIR", "/tmp")

    sys.modules.pop("whisper_batch.app.main", None)
    m = importlib.import_module("whisper_batch.app.main")

    # 定数上書き（env 反映漏れ対策）
    m.PROCESS_TIMEOUT_SECONDS = 5
    m.DURATION_TIMEOUT_FACTOR = 1.0
    m.POLL_INTERVAL_SECONDS = 1
    m.COLLECTION = collection_name
    return m

# ── 重い依存をスタブ化（convert_audio 呼び出し確認用） ─────────────

@pytest.fixture()
def _stub_heavy_dependencies_convert(monkeypatch, tmp_path, main_module):
    """
    ・GCS クライアントをダミー
    ・check_audio_format=False / convert_audio=Mock()
    ・残りの重い関数は no-op
    """
    # storage.Client
    storage_stub = types.ModuleType("storage_stub")
    class _Bucket:  # noqa: D401
        def blob(self, *_a, **_kw): return mock.MagicMock()
    storage_stub.Client = lambda *_a, **_kw: mock.MagicMock(bucket=lambda *_a, **_kw: _Bucket())
    monkeypatch.setattr(main_module, "storage", storage_stub, raising=True)

    # heavy funcs
    import whisper_batch.app.main as _m
    monkeypatch.setattr(_m, "check_audio_format",
                        mock.create_autospec(_m.check_audio_format, return_value=False),
                        raising=True)
    convert_mock = mock.create_autospec(_m.convert_audio, return_value=None)
    monkeypatch.setattr(_m, "convert_audio", convert_mock, raising=True)
    for fn in ("transcribe_audio", "diarize_audio", "combine_results"):
        monkeypatch.setattr(_m, fn, mock.create_autospec(getattr(_m, fn), return_value=None), raising=True)

    # shutil.copy2 は no-op
    import shutil
    monkeypatch.setattr(shutil, "copy2", lambda *a, **k: None, raising=True)

    # TMP_ROOT を tmp_path
    _m.TMP_ROOT = Path(tmp_path)

    return convert_mock  # 呼び出し検証に使う

# ── テストケース ───────────────────────────────────────────────

def test_mark_timeout_jobs_long_audio_no_timeout(
    firestore_client, main_module, collection_name
):
    """
    audio_duration_ms が長いため PROCESS_TIMEOUT_SECONDS を超えても
    まだタイムアウトしないことを確認
    """
    col = firestore_client.collection(collection_name)
    long_audio_ms = 600_000  # 10 分
    _add_job(
        col,
        "processing",
        audio_duration_ms=long_audio_ms,
        created_at=_utcnow(),
        process_started_at=_utcnow() - _dt.timedelta(seconds=100),  # 100 秒経過
    )
    before_failed = _count(col, "failed")

    main_module._mark_timeout_jobs(firestore_client)  # type: ignore[arg-type]

    after_failed = _count(col, "failed")
    assert after_failed == before_failed, "DURATION_TIMEOUT_FACTOR に基づき failed へ遷移しないはず"

def test_process_job_invokes_convert_audio(
    firestore_client, main_module, collection_name, _stub_heavy_dependencies_convert
):
    """
    check_audio_format=False パスで convert_audio が 1 回呼ばれること
    """
    convert_mock = _stub_heavy_dependencies_convert
    col = firestore_client.collection(collection_name)
    job_id = _add_job(
        col,
        "processing",
        filename="dummy.mp3",  # WAV 以外にしておく
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    job_dict = col.document(job_id).get().to_dict()
    job_dict["job_id"] = job_id

    main_module._process_job(firestore_client, job_dict)  # type: ignore[arg-type]

    assert convert_mock.called, "check_audio_format=False の場合 convert_audio を呼ぶはず"
    status = col.document(job_id).get().to_dict()["status"]
    assert status == "completed"

def test_process_job_marks_failed_on_validation_error(
    firestore_client, main_module, collection_name
):
    """
    必須フィールド欠落で WhisperFirestoreData バリデーションが失敗した際
    status が failed になることを確認
    """
    col = firestore_client.collection(collection_name)
    job_id = _add_job(
        col,
        "processing",
        filename="to_be_removed.wav",
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    job_dict = col.document(job_id).get().to_dict()
    job_dict["job_id"] = job_id
    job_dict.pop("filename")  # filename を欠落させてバリデーションエラーを誘発

    main_module._process_job(firestore_client, job_dict)  # type: ignore[arg-type]

    snap = col.document(job_id).get()
    data = snap.to_dict()
    assert data["status"] == "failed"
    assert "データモデル検証エラー" in data.get("error_message", "")
