"""
tests/app/tests_whisper_batch3.py

目的
--------------------------------------------------
1. 追加エッジケースの単体テスト
   - process_started_at が無い processing ドキュメントは
     _mark_timeout_jobs が無視すること
   - queued が 0 件の場合に _pick_next_job が None を返し
     Firestore 更新を行わないこと
2. 完了 / 失敗ハンドリングのガード確認
   - _process_job が終了時に Firestore ドキュメントの
     現在ステータスを再確認し、processing 以外なら
     update しないこと（成功パス・例外パス両方）

Firestore エミュレータを使う統合寄りテストと、
unittest.mock を使う高速単体テストをバランスさせた
スイート構成になっています。
"""

from __future__ import annotations

import datetime as _dt
import importlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from unittest import mock

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP, DocumentSnapshot

# ---------------------------------------------------------------------------
# 低レイヤ util
# ---------------------------------------------------------------------------


def _utcnow() -> _dt.datetime:
    """UTC now (tz aware) を返す"""
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _rand_suffix() -> str:
    """コレクション名衝突を防ぐ一意 suffix"""
    import uuid

    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# pytest 固定フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def firestore_client() -> firestore.Client:  # type: ignore[valid-type]
    """
    Firestore エミュレータへ接続するクライアントを用意
    環境変数 FIRESTORE_EMULATOR_HOST 未設定ならテストを skip
    """
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        pytest.skip("FIRESTORE_EMULATOR_HOST が未設定のため Firestore 統合テストをスキップ")
    return firestore.Client(project=f"test-{_rand_suffix()}")


@pytest.fixture(scope="session")
def collection_name() -> str:
    """テスト用コレクション名を返す（毎回固有）"""
    return f"whisper_jobs_test_{_rand_suffix()}"


@pytest.fixture(scope="session")
def main_module(collection_name: str):
    """
    whisper_batch.app.main を “テスト用設定” で再ロードしたモジュールを返す
    """
    # モジュール import 前に環境変数を書き換える
    os.environ["WHISPER_JOBS_COLLECTION"] = collection_name
    os.environ["PROCESS_TIMEOUT_SECONDS"] = "5"
    os.environ["AUDIO_TIMEOUT_MULTIPLIER"] = "1.0"
    os.environ["POLL_INTERVAL_SECONDS"] = "1"
    os.environ.setdefault("DEVICE", "cpu")
    os.environ.setdefault("LOCAL_TMP_DIR", "/tmp")

    # 既に読み込まれていたら捨てる
    if "whisper_batch.app.main" in importlib.sys.modules:
        del importlib.sys.modules["whisper_batch.app.main"]

    main = importlib.import_module("whisper_batch.app.main")

    # env→定数 反映漏れ対策
    main.PROCESS_TIMEOUT_SECONDS = 5
    main.DURATION_TIMEOUT_FACTOR = 1.0
    main.POLL_INTERVAL_SECONDS = 1
    main.COLLECTION = collection_name

    return main


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------

_REQUIRED_BASE_FIELDS: Dict[str, object] = {
    "user_id": "u01",
    "user_email": "tester@example.com",
    "filename": "dummy.wav",
    "description": "",
    "recording_date": "2025-05-05",
    "gcs_bucket_name": "dummy-bucket",
    "audio_size": 1234,
    "audio_duration_ms": 1_000,
    "file_hash": "deadbeef",
    "language": "ja",
    "initial_prompt": "",
    "tags": [],
}


def _add_job(
    col_ref: firestore.CollectionReference,  # type: ignore[valid-type]
    status: str,
    **extra_fields,
) -> str:
    """コレクションへ 1 件追加し、ドキュメント ID を返す"""
    data = {**_REQUIRED_BASE_FIELDS, **extra_fields, "status": status}
    doc_ref = col_ref.document()
    doc_ref.set(data)
    return doc_ref.id


def _count_by_status(
    col_ref: firestore.CollectionReference, status: str  # type: ignore[valid-type]
) -> int:
    return len(list(col_ref.where("status", "==", status).stream()))


# ---------------------------------------------------------------------------
# 1) _mark_timeout_jobs ── process_started_at が無いものは無視
# ---------------------------------------------------------------------------


def test_mark_timeout_jobs_skip_when_no_process_started(
    firestore_client: firestore.Client,  # type: ignore[valid-type]
    main_module,
    collection_name: str,
):
    col = firestore_client.collection(collection_name)
    # process_started_at なし processing を 1 つ作成
    _add_job(col, "processing")  # ← process_started_at フィールドなし

    before_failed = _count_by_status(col, "failed")

    main_module._mark_timeout_jobs(firestore_client)  # type: ignore[arg-type]

    # failed が増えないことを検証
    after_failed = _count_by_status(col, "failed")
    assert after_failed == before_failed


# ---------------------------------------------------------------------------
# 2) _pick_next_job ── queued が 0 件なら None を返す
# ---------------------------------------------------------------------------


def test_pick_next_job_returns_none_when_queue_empty(
    firestore_client: firestore.Client,  # type: ignore[valid-type]
    main_module,
    collection_name: str,
):
    col = firestore_client.collection(collection_name)
    assert _count_by_status(col, "queued") == 0, "前提: queued は 0 件"

    job = main_module._pick_next_job(firestore_client)  # type: ignore[arg-type]
    assert job is None, "queued が無い場合は None を返す"


# ---------------------------------------------------------------------------
# 3) _process_job 完了パス ── status 変化済みなら更新しない
# ---------------------------------------------------------------------------


@pytest.fixture()
def _stub_heavy_dependencies(monkeypatch, tmp_path):
    """
    _process_job が依存する重い I/O・ML 関数をすべてスタブ化
    """
    # ----- storage.Client をダミー化 ----------------------------------------
    class _DummyBlob:
        def download_to_filename(self, *_a, **_kw): ...
        def upload_from_filename(self, *_a, **_kw): ...

    class _DummyBucket:
        def blob(self, *_a):  # noqa: D401
            return _DummyBlob()

    class _DummyStorageClient:
        def bucket(self, *_a):  # noqa: D401
            return _DummyBucket()

    monkeypatch.setitem(sys.modules, "google.cloud.storage", mock.MagicMock())
    import google.cloud.storage  # type: ignore

    monkeypatch.setattr(google.cloud.storage, "Client", _DummyStorageClient)

    # ----- Whisper / FFmpeg などの関数を no-op 化 ----------------------------
    nop = lambda *a, **kw: None  # noqa: E731
    monkeypatch.setattr("whisper_batch.app.main.check_audio_format", lambda *_a, **_kw: True)
    for fn in (
        "convert_audio",
        "transcribe_audio",
        "diarize_audio",
        "combine_results",
    ):
        monkeypatch.setattr(f"whisper_batch.app.main.{fn}", nop)

    # ----- 一時ディレクトリをテスト用 tmp_path に差し替え ------------------
    from whisper_batch.app import main as _m

    _m.TMP_ROOT = Path(tmp_path)


def test_process_job_skip_update_if_status_already_completed(
    firestore_client: firestore.Client,  # type: ignore[valid-type]
    main_module,
    collection_name: str,
    _stub_heavy_dependencies,
):
    """
    処理完了直前に別プロセス等で status が processing → completed に
    変わっていた場合、_process_job は Firestore 更新をスキップするか
    （＝completed のまま残るか）を確認
    """
    col = firestore_client.collection(collection_name)

    # ① processing ジョブを投入
    job_id = _add_job(
        col,
        "processing",
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    # ② 取得して _process_job に渡す辞書を用意
    job_dict = col.document(job_id).get().to_dict()
    job_dict["job_id"] = job_id  # _process_job の期待仕様

    # ③ 処理中に競合更新が起きた想定で status を completed に変更
    col.document(job_id).update({"status": "completed"})

    # ④ _process_job を実行（成功パス）
    main_module._process_job(firestore_client, job_dict)  # type: ignore[arg-type]

    final_status = col.document(job_id).get().to_dict()["status"]
    assert final_status == "completed", "processing 以外なら更新しないはず"  # 期待どおり


# ---------------------------------------------------------------------------
# 4) _process_job 例外パス ── status 変化済みなら failed にしない
# ---------------------------------------------------------------------------


def test_process_job_skip_failed_update_on_error_if_status_changed(
    firestore_client: firestore.Client,  # type: ignore[valid-type]
    main_module,
    collection_name: str,
    _stub_heavy_dependencies,
    monkeypatch,
):
    """
    _process_job 途中で例外発生 & その時点で status が already completed
    → except 節の failed 更新がスキップされるかを検証
    """
    col = firestore_client.collection(collection_name)

    # processing ジョブ
    job_id = _add_job(
        col,
        "processing",
        created_at=_utcnow(),
        process_started_at=_utcnow(),
    )
    job_dict = col.document(job_id).get().to_dict()
    job_dict["job_id"] = job_id

    # convert_audio を強制的に例外を投げるダミーに差し替え
    def _boom(*_a, **_kw):
        raise RuntimeError("forced error")

    monkeypatch.setattr("whisper_batch.app.main.convert_audio", _boom)

    # 途中で外部プロセスが completed にしてしまった想定
    col.document(job_id).update({"status": "completed"})

    # 例外は _process_job 内で握りつぶされるはず
    main_module._process_job(firestore_client, job_dict)  # type: ignore[arg-type]

    final_status = col.document(job_id).get().to_dict()["status"]
    # failed にならず completed のまま
    assert final_status == "completed", "例外パスでも processing 以外なら failed 更新をスキップ"

