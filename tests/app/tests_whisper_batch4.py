"""
tests/app/tests_whisper_batch4.py

Firestore エミュレーター上で whisper_batch.app.main を直接たたく
統合テスト／単体テスト混在スイート。実行例:

    $ export FIRESTORE_EMULATOR_HOST=localhost:8900
    $ pytest tests/app/tests_whisper_batch4.py -v

ヘルパー関数のスキーマとテスト着想は既存
tests_whisper_batch3.py をベースに改良した。:contentReference[oaicite:0]{index=0}
"""

from __future__ import annotations

import datetime as _dt
import importlib
import os
import sys
import types
import uuid
from pathlib import Path
from typing import Dict, cast
from unittest import mock

import json
import pytest
from google.cloud import firestore


# ────────────────────────────────────────────────────────────────────────────
# 低レイヤ util
# ────────────────────────────────────────────────────────────────────────────


def _utcnow() -> _dt.datetime:
    """tz-aware UTC now を返す"""
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _rand_suffix() -> str:
    """コレクション名衝突を防ぐ一意 suffix"""
    return uuid.uuid4().hex[:8]


def _add_job(
    col_ref: firestore.CollectionReference,  # type: ignore[valid-type]
    status: str,
    **extra,
) -> str:
    """
    コレクションへ 1 件追加しドキュメント ID を返す
    Firestore スキーマは whisper_batch 仕様に最低限合わせる
    """
    base: Dict[str, object] = {
        "user_id": "u01",
        "user_email": "tester@example.com",
        "filename": "dummy.wav",
        "description": "",
        "recording_date": "2025-05-05",
        "gcs_bucket_name": "dummy-bucket",
        "audio_size": 1234,
        "audio_duration_ms": 10_000,
        "file_hash": "deadbeef",
        "language": "ja",
        "initial_prompt": "",
        "tags": [],
        # speaker related
        "num_speakers": None,
        "min_speakers": 1,
        "max_speakers": 1,
    }
    base.update(extra)
    base["status"] = status
    doc_ref = col_ref.document()
    doc_ref.set(base)
    return cast(str, doc_ref.id)


def _count_by_status(
    col_ref: firestore.CollectionReference, status: str  # type: ignore[valid-type]
) -> int:
    """同 status 件数を数える"""
    return len(list(col_ref.where("status", "==", status).stream()))


# ────────────────────────────────────────────────────────────────────────────
# pytest 固定フィクスチャ
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def firestore_client() -> firestore.Client:  # type: ignore[valid-type]
    """
    Firestore エミュレータへ接続するクライアント
    未起動ならスキップ
    """
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        pytest.skip("FIRESTORE_EMULATOR_HOST が未設定 – エミュレータを起動して下さい")
    return firestore.Client(project=f"test-{_rand_suffix()}")


@pytest.fixture(scope="session")
def collection_name() -> str:
    """テスト用コレクション名を返す（毎回固有）"""
    return f"whisper_jobs_test_{_rand_suffix()}"


@pytest.fixture(scope="session")
def main_module(collection_name: str):
    """
    whisper_batch.app.main を “テスト用設定” で再ロードして返す
    """
    # env で高速化
    os.environ["WHISPER_JOBS_COLLECTION"] = collection_name
    os.environ["PROCESS_TIMEOUT_SECONDS"] = "5"
    os.environ["AUDIO_TIMEOUT_MULTIPLIER"] = "1.0"
    os.environ["POLL_INTERVAL_SECONDS"] = "1"
    os.environ.setdefault("DEVICE", "cpu")
    os.environ.setdefault("LOCAL_TMP_DIR", "/tmp")

    # 既存 import を破棄して再ロード
    sys.modules.pop("whisper_batch.app.main", None)
    main = importlib.import_module("whisper_batch.app.main")

    # env→定数 反映漏れ対策
    main.PROCESS_TIMEOUT_SECONDS = 5
    main.DURATION_TIMEOUT_FACTOR = 1.0
    main.POLL_INTERVAL_SECONDS = 1
    main.COLLECTION = collection_name
    return main


# ────────────────────────────────────────────────────────────────────────────
# 重い依存をスタブ化 (autospec=True)
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def _stub_heavy_dependencies(monkeypatch, tmp_path):
    """
    Whisper / FFmpeg / PyAnnote / GCS をすべて no-op 化しつつ
    autospec=True でシグネチャ検証も行う
    """
    # ---- google.cloud.storage.Client 置換 ----------------------------------
    storage_stub = types.ModuleType("google.cloud.storage")

    class _DummyBlob:
        download_to_filename = lambda *a, **kw: None
        download_as_text = lambda *a, **kw: ""
        upload_from_filename = lambda *a, **kw: None
        upload_from_string = lambda *a, **kw: None

    class _DummyBucket:
        def blob(self, *_a, **_kw):
            return _DummyBlob()

    class _DummyStorageClient:
        def bucket(self, *_a, **_kw):
            return _DummyBucket()

    storage_stub.Client = _DummyStorageClient
    sys.modules["google.cloud.storage"] = storage_stub

    # ---- heavy 関数を autospec で差し替え ----------------------------------
    import whisper_batch.app.main as _m

    for fn_name in ("convert_audio", "transcribe_audio", "diarize_audio", "combine_results"):
        orig = getattr(_m, fn_name)
        monkeypatch.setattr(_m, fn_name, mock.create_autospec(orig, return_value=None), raising=True)

    monkeypatch.setattr(
        _m,
        "check_audio_format",
        mock.create_autospec(_m.check_audio_format, return_value=True),
        raising=True,
    )

    # ---- 一時ディレクトリを tmp_path に ------------------------------------
    _m.TMP_ROOT = Path(tmp_path)


# ────────────────────────────────────────────────────────────────────────────
# 1) _mark_timeout_jobs
# ────────────────────────────────────────────────────────────────────────────


def test_mark_timeout_jobs_skip_when_no_process_started(
    firestore_client,
    main_module,
    collection_name,
):
    col = firestore_client.collection(collection_name)
    _add_job(col, "processing")  # process_started_at 無し

    before = _count_by_status(col, "failed")
    main_module._mark_timeout_jobs(firestore_client)
    after = _count_by_status(col, "failed")

    assert after == before, "process_started_at 無しは failed にしない"


# ────────────────────────────────────────────────────────────────────────────
# 2) _pick_next_job
# ────────────────────────────────────────────────────────────────────────────


def test_pick_next_job_returns_none_when_queue_empty(
    firestore_client,
    main_module,
    collection_name,
):
    col = firestore_client.collection(collection_name)
    assert _count_by_status(col, "queued") == 0

    job = main_module._pick_next_job(firestore_client)
    assert job is None, "queued が無いときは None"


# ────────────────────────────────────────────────────────────────────────────
# 3) _process_job – 通常完了パス
# ────────────────────────────────────────────────────────────────────────────


def test_process_job_completes_successfully(
    firestore_client,
    main_module,
    collection_name,
    _stub_heavy_dependencies,
):
    col = firestore_client.collection(collection_name)
    job_id = _add_job(
        col,
        "processing",
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    job_dict = col.document(job_id).get().to_dict()
    job_dict["job_id"] = job_id  # _process_job の期待仕様

    main_module._process_job(firestore_client, job_dict)
    status = col.document(job_id).get().to_dict()["status"]
    assert status == "completed"


# ────────────────────────────────────────────────────────────────────────────
# 4) _process_job – 例外発生 → failed
# ────────────────────────────────────────────────────────────────────────────


def test_process_job_marks_failed_on_exception(
    firestore_client,
    main_module,
    collection_name,
    monkeypatch,
    _stub_heavy_dependencies,
):
    col = firestore_client.collection(collection_name)
    job_id = _add_job(
        col,
        "processing",
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    job_dict = col.document(job_id).get().to_dict()
    job_dict["job_id"] = job_id

    # convert_audio を例外化
    import whisper_batch.app.main as _m

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated error")

    monkeypatch.setattr(
        _m,
        "convert_audio",
        mock.create_autospec(_m.convert_audio, side_effect=_boom),
        raising=True,
    )

    main_module._process_job(firestore_client, job_dict)
    status = col.document(job_id).get().to_dict()["status"]
    assert status == "failed"
