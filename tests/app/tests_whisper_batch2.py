"""
tests/app/tests_whisper_batch.py

前提:
  * Google Cloud Firestore エミュレータが起動済み
      $ gcloud beta emulators firestore start --host-port=localhost:8900 &
  * 環境変数 FIRESTORE_EMULATOR_HOST=localhost:8900 が設定済み
  * poetry / pip 等で google-cloud-firestore をインストール済み
  * whisper_batch パッケージが import 可能

テスト内容:
  1) _mark_timeout_jobs()
        - タイムアウト超過ジョブを failed にする
        - まだ時間内のジョブは変更しない
  2) _pick_next_job()
        - 最古の queued ジョブを processing に変更し、
          検証済み辞書を返す
"""

from __future__ import annotations

import datetime as _dt
import importlib
import os
import uuid
from pathlib import Path
from typing import Dict, List

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

# ---------------------------------------------------------------------------
# 低レイヤ util
# ---------------------------------------------------------------------------


def _utcnow() -> _dt.datetime:
    """UTC now (tz aware) を返す"""
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _rand_suffix() -> str:
    """コレクション名衝突を防ぐ一意 suffix"""
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# pytest 固定フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def firestore_client() -> firestore.Client:  # type: ignore
    """
    Firestore エミュレータへ接続するクライアントを用意
    環境変数 FIRESTORE_EMULATOR_HOST 未設定ならテストを skip
    """
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        pytest.skip("FIRESTORE_EMULATOR_HOST が未設定のため Firestore 統合テストをスキップ")

    # プロジェクト ID はランダムにしておくと衝突しにくい
    project = f"test-{_rand_suffix()}"
    return firestore.Client(project=project)


@pytest.fixture(scope="session")
def collection_name() -> str:
    """テスト用コレクション名を返す（毎回固有）"""
    return f"whisper_jobs_test_{_rand_suffix()}"


@pytest.fixture(scope="session")
def main_module(collection_name: str):
    """
    whisper_batch.app.main を “テスト用設定” で再ロードしたモジュールを返す
    - タイムアウト時間などを小さくパッチ
    - COLLECTION をテスト用コレクションに差し替え
    """
    # モジュール import 前に環境変数を書き換える
    os.environ["WHISPER_JOBS_COLLECTION"] = collection_name
    # もともとの env が長い場合でもテストを高速化
    os.environ["PROCESS_TIMEOUT_SECONDS"] = "5"
    os.environ["AUDIO_TIMEOUT_MULTIPLIER"] = "1.0"
    os.environ["POLL_INTERVAL_SECONDS"] = "1"
    os.environ.setdefault("DEVICE", "cpu")           # GPU 不要
    os.environ.setdefault("LOCAL_TMP_DIR", "/tmp")   # 一時 dir

    # すでに読み込まれている場合は捨てる
    if "whisper_batch.app.main" in importlib.sys.modules:
        del importlib.sys.modules["whisper_batch.app.main"]

    main = importlib.import_module("whisper_batch.app.main")

    # 念のため数値パラメータを上書き（env 反映漏れ対策）
    main.PROCESS_TIMEOUT_SECONDS = 5
    main.DURATION_TIMEOUT_FACTOR = 1.0
    main.POLL_INTERVAL_SECONDS = 1
    main.COLLECTION = collection_name

    return main


# ---------------------------------------------------------------------------
# ジョブ作成ユーティリティ
# ---------------------------------------------------------------------------


_REQUIRED_BASE_FIELDS: Dict[str, object] = {
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
    # 話者関連
    "num_speakers": None,
    "min_speakers": 1,
    "max_speakers": 1,
}


def _add_job(
    col_ref: firestore.CollectionReference,  # type: ignore
    status: str,
    **extra_fields,
) -> str:
    """
    コレクションへ 1 件追加し、ドキュメント ID を返す
    """
    data: Dict[str, object] = {**_REQUIRED_BASE_FIELDS, **extra_fields}
    data["status"] = status
    col_ref.document().set(data)
    return cast(str, "")  # satisfy type checker


def _prepare_dummy_jobs(col_ref: firestore.CollectionReference):  # type: ignore
    """
    テストケースで必要な文書を一気に投入
    """
    now = _utcnow()

    # ① queued（2 件）
    col_ref.add({**_REQUIRED_BASE_FIELDS, "status": "queued", "created_at": now})
    col_ref.add(
        {**_REQUIRED_BASE_FIELDS, "status": "queued", "created_at": now + _dt.timedelta(seconds=1)}
    )

    # ② processing で まだタイムアウトしていない
    col_ref.add(
        {
            **_REQUIRED_BASE_FIELDS,
            "status": "processing",
            "created_at": now,
            "process_started_at": now,  # 直近 → セーフ
            "audio_duration_ms": 2_000,  # 2 秒
        }
    )

    # ③ processing で タイムアウト超過
    col_ref.add(
        {
            **_REQUIRED_BASE_FIELDS,
            "status": "processing",
            "created_at": now - _dt.timedelta(minutes=10),
            # 30 秒前に開始した想定 → 5 秒閾値を超える
            "process_started_at": now - _dt.timedelta(seconds=30),
            "audio_duration_ms": 1_000,  # 1 秒
        }
    )

    # ④ processing だが process_started_at が無い（スキップ対象）
    col_ref.add({**_REQUIRED_BASE_FIELDS, "status": "processing"})


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------


def _count_by_status(col: firestore.CollectionReference, status: str) -> int:  # type: ignore
    """status 別に件数をカウント"""
    return len(list(col.where("status", "==", status).stream()))


@pytest.fixture(autouse=True)
def _setup_firestore_data(
    firestore_client: firestore.Client,  # type: ignore
    collection_name: str,
):
    """
    各テストの実行前にコレクションをクリアしてダミーデータ投入
    """
    col_ref = firestore_client.collection(collection_name)

    # コレクションを一旦空に
    for doc in col_ref.stream():
        doc.reference.delete()

    _prepare_dummy_jobs(col_ref)

    yield  # テストを実行

    # 後始末: なるべくクリーンにしておく
    for doc in col_ref.stream():
        doc.reference.delete()


# ---------------------------------------------------------------------------
# 1) _mark_timeout_jobs
# ---------------------------------------------------------------------------


def test_mark_timeout_jobs_marks_failed(
    firestore_client: firestore.Client,  # type: ignore
    main_module,
    collection_name: str,
):
    """
    タイムアウトを超過している processing ジョブが failed へ更新されるか
    """
    col = firestore_client.collection(collection_name)

    # 前提確認
    before_failed = _count_by_status(col, "failed")
    assert before_failed == 0, "事前状態: failed ドキュメントは 0 件のはず"

    # ---- 対象関数実行 ----
    main_module._mark_timeout_jobs(firestore_client)  # type: ignore

    # 検証
    after_failed = _count_by_status(col, "failed")
    assert after_failed == 1, "タイムアウト超過分のみ failed へ変わるはず"


def test_mark_timeout_jobs_no_update_when_within_timeout(
    firestore_client: firestore.Client,  # type: ignore
    main_module,
    collection_name: str,
):
    """
    まだタイムアウトしていない processing ジョブは変更されないか
    """
    col = firestore_client.collection(collection_name)

    # 関数実行前の processing 件数
    before_processing = _count_by_status(col, "processing")

    # ---- 対象関数実行 ----
    main_module._mark_timeout_jobs(firestore_client)  # type: ignore

    # processing → failed が 1 件起きる想定なので、
    # 残り processing 件数は (before - 1) になる
    after_processing = _count_by_status(col, "processing")
    assert after_processing == before_processing - 1, "タイムアウト対象のみ減少するはず"


# ---------------------------------------------------------------------------
# 2) _pick_next_job
# ---------------------------------------------------------------------------


def test_pick_next_job_returns_valid_job_and_updates_status(
    firestore_client: firestore.Client,  # type: ignore
    main_module,
    collection_name: str,
):
    """
    _pick_next_job が:
      * 最古の queued を取得して返す
      * その status を processing へ更新する
    """
    col = firestore_client.collection(collection_name)

    # queued の数を確認
    initial_queued = _count_by_status(col, "queued")
    assert initial_queued >= 2, "前提: queued ドキュメントが 2 件以上あること"

    # ---- 対象関数実行 ----
    job_dict = main_module._pick_next_job(firestore_client)  # type: ignore

    # 返り値検証
    assert job_dict is not None, "_pick_next_job は None であってはならない"
    assert job_dict["status"] == "processing"

    job_id = job_dict["job_id"]
    snap: DocumentSnapshot = col.document(job_id).get()

    # Firestore 上の status が processing へ変わったか
    assert snap.exists
    assert snap.to_dict().get("status") == "processing"

    # queued の減少 + processing の増加を確認
    queued_after = _count_by_status(col, "queued")
    processing_after = _count_by_status(col, "processing")
    assert queued_after == initial_queued - 1
    assert processing_after >= 2  # 既存 processing + 1 新規分
