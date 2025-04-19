import pytest
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch
from google.cloud import firestore

# テスト対象の関数をインポート
from whisper_queue.app.main import process_next_job, create_batch_job

# テスト用のFirestoreセットアップユーティリティをインポート
from tests.app.firebase_t import (
    load_environment,
    initialize_firestore,
    clear_collection,
    create_test_data,
    list_collection_docs
)

# テスト前に環境を設定するフィクスチャ
@pytest.fixture(scope="module")
def setup_environment():
    """環境変数を設定するフィクスチャ"""
    # 環境変数を読み込む
    load_environment()
    
    # テスト用の環境変数を設定
    with patch.dict('os.environ', {
        'MAX_PROCESSING_JOBS': '3',  # 同時処理数上限
        'WHISPER_JOBS_COLLECTION': 'test_whisper_jobs'  # テスト用コレクション
    }):
        yield

# テスト用のFirestoreクライアントを準備するフィクスチャ
@pytest.fixture(scope="module")
def firestore_client(setup_environment):
    """実際のFirestoreクライアントを初期化するフィクスチャ"""
    db = initialize_firestore()
    if not db:
        pytest.fail("Firestoreクライアントの初期化に失敗しました")
    
    # テスト用のコレクション名を取得
    collection_name = os.environ.get('WHISPER_JOBS_COLLECTION', 'test_whisper_jobs')
    
    # テスト前にコレクションをクリア
    clear_collection(db, collection_name)
    
    yield db
    
    # テスト後もコレクションをクリア
    clear_collection(db, collection_name)

# 各テストケース用にFirestoreデータをセットアップするフィクスチャ
@pytest.fixture
def setup_test_data(firestore_client):
    """テストデータをセットアップし、テスト後にクリーンアップするフィクスチャ"""
    # テスト用のコレクション名を取得
    collection_name = os.environ.get('WHISPER_JOBS_COLLECTION', 'test_whisper_jobs')
    
    # コレクションをクリア
    clear_collection(firestore_client, collection_name)
    
    # フィクスチャが使用された後にクリーンアップするためのセットアップデータを返す
    def _setup_data(config=None):
        if config is None:
            config = {'queued': 5, 'processing': 2, 'completed': 3, 'failed': 2, 'canceled': 1}
        
        # テストデータを作成
        create_test_data(firestore_client, collection_name, config)
        
        # テストデータのドキュメント一覧を表示
        list_collection_docs(firestore_client, collection_name)
        
        # configをそのまま返してテスト関数で使用できるようにする
        return config
    
    return _setup_data

# create_batch_job関数をモックするフィクスチャ
@pytest.fixture
def mock_create_batch_job():
    """create_batch_job関数をモックするフィクスチャ"""
    with patch('whisper_queue.app.main.create_batch_job') as mock:
        # 成功時のバッチジョブ名を返すようにモック
        mock.return_value = f"whisper-test-job-{int(time.time())}"
        yield mock

# テストケース1: 処理待ちのジョブがありスロットが空いている場合
def test_process_next_job_with_available_slots(setup_environment, setup_test_data, mock_create_batch_job):
    """処理待ちのジョブがあり、スロットが空いている場合のテスト"""
    # テストデータをセットアップ - 処理中が1、待ち行列に3のジョブを用意
    setup_test_data({'queued': 3, 'processing': 1, 'completed': 0, 'failed': 0, 'canceled': 0})
    
    # テスト前のデータベース状態を確認
    db = initialize_firestore()
    collection_name = os.environ.get('WHISPER_JOBS_COLLECTION', 'test_whisper_jobs')
    
    # 処理前の状態をログに出力
    print("\n=== テスト実行前のデータベース状態 ===")
    processing_before = list(db.collection(collection_name).where("status", "==", "processing").stream())
    queued_before = list(db.collection(collection_name).where("status", "==", "queued").stream())
    print(f"処理中のジョブ数: {len(processing_before)}")
    print(f"待ち行列のジョブ数: {len(queued_before)}")
    for doc in processing_before:
        print(f"処理中ジョブID: {doc.id}")
    for doc in queued_before:
        print(f"待機中ジョブID: {doc.id}")
    
    # process_next_job関数を実行
    process_next_job()
    
    # テスト後のデータベース状態を確認
    print("\n=== テスト実行後のデータベース状態 ===")
    processing_after = list(db.collection(collection_name).where("status", "==", "processing").stream())
    queued_after = list(db.collection(collection_name).where("status", "==", "queued").stream())
    print(f"処理中のジョブ数: {len(processing_after)}")
    print(f"待ち行列のジョブ数: {len(queued_after)}")
    for doc in processing_after:
        print(f"処理中ジョブID: {doc.id}")
    for doc in queued_after:
        print(f"待機中ジョブID: {doc.id}")
    
    # 検証：バッチジョブが作成されたか確認
    # MAX_PROCESSING_JOBS=3, 現在処理中=1なので、2つのジョブが処理されるはず
    assert mock_create_batch_job.call_count == 2
    
    # 状態の変化を検証
    assert len(processing_after) == 3  # 元々1つ + 新たに2つ追加
    assert len(queued_after) == 1  # 元々3つ - 処理された2つ = 1つ残る

# テストケース2: 処理スロットが空いていない場合
def test_process_next_job_no_available_slots(setup_environment, setup_test_data, mock_create_batch_job):
    """スロットが空いていない場合のテスト"""
    # テストデータをセットアップ - 処理上限数のジョブが処理中
    setup_test_data({'queued': 3, 'processing': 3, 'completed': 0, 'failed': 0, 'canceled': 0})
    
    # バッチジョブ作成モックの呼び出しカウントをリセット
    mock_create_batch_job.reset_mock()
    
    # process_next_job関数を実行
    process_next_job()
    
    # 検証：バッチジョブが作成されていないことを確認
    mock_create_batch_job.assert_not_called()
    
    # Firestoreのドキュメントを検証
    db = initialize_firestore()
    collection_name = os.environ.get('WHISPER_JOBS_COLLECTION', 'test_whisper_jobs')
    
    # 処理中のジョブ数が変わっていないことを確認
    processing_count = len(list(db.collection(collection_name)
                                .where("status", "==", "processing")
                                .stream()))
    assert processing_count == 3  # 変化なし
    
    # 待ち行列のジョブ数が変わっていないことを確認
    queued_count = len(list(db.collection(collection_name)
                           .where("status", "==", "queued")
                           .stream()))
    assert queued_count == 3  # 変化なし

# テストケース3: 処理待ちのジョブがない場合
def test_process_next_job_no_queued_jobs(setup_environment, setup_test_data, mock_create_batch_job):
    """処理待ちのジョブがない場合のテスト"""
    # テストデータをセットアップ - 待ち行列にジョブなし
    setup_test_data({'queued': 0, 'processing': 1, 'completed': 3, 'failed': 0, 'canceled': 0})
    
    # バッチジョブ作成モックの呼び出しカウントをリセット
    mock_create_batch_job.reset_mock()
    
    # process_next_job関数を実行
    process_next_job()
    
    # 検証：バッチジョブが作成されていないことを確認
    mock_create_batch_job.assert_not_called()
    
    # Firestoreのドキュメントを検証
    db = initialize_firestore()
    collection_name = os.environ.get('WHISPER_JOBS_COLLECTION', 'test_whisper_jobs')
    
    # 処理中のジョブ数が変わっていないことを確認
    processing_count = len(list(db.collection(collection_name)
                                .where("status", "==", "processing")
                                .stream()))
    assert processing_count == 1  # 変化なし

# テストケース4: バッチジョブ作成時にエラーが発生する場合
def test_process_next_job_batch_creation_error(setup_environment, setup_test_data):
    """バッチジョブ作成時にエラーが発生する場合のテスト"""
    # テストデータをセットアップ
    setup_test_data({'queued': 2, 'processing': 0, 'completed': 0, 'failed': 0, 'canceled': 0})
    
    # テスト前のデータベース状態を確認
    db = initialize_firestore()
    collection_name = os.environ.get('WHISPER_JOBS_COLLECTION', 'test_whisper_jobs')
    
    # 処理前の状態をログに出力
    print("\n=== エラーテスト実行前のデータベース状態 ===")
    processing_before = list(db.collection(collection_name).where("status", "==", "processing").stream())
    queued_before = list(db.collection(collection_name).where("status", "==", "queued").stream())
    failed_before = list(db.collection(collection_name).where("status", "==", "failed").stream())
    print(f"処理中のジョブ数: {len(processing_before)}")
    print(f"待ち行列のジョブ数: {len(queued_before)}")
    print(f"失敗したジョブ数: {len(failed_before)}")
    for doc in queued_before:
        print(f"待機中ジョブID: {doc.id}")
    
    # create_batch_job関数がエラーを発生させるようにモック
    with patch('whisper_queue.app.main.create_batch_job') as mock:
        mock.side_effect = Exception("バッチジョブ作成エラー")
        
        # process_next_job関数を実行
        process_next_job()
    
    # テスト後のデータベース状態を確認
    print("\n=== エラーテスト実行後のデータベース状態 ===")
    processing_after = list(db.collection(collection_name).where("status", "==", "processing").stream())
    queued_after = list(db.collection(collection_name).where("status", "==", "queued").stream())
    failed_after = list(db.collection(collection_name).where("status", "==", "failed").stream())
    print(f"処理中のジョブ数: {len(processing_after)}")
    print(f"待ち行列のジョブ数: {len(queued_after)}")
    print(f"失敗したジョブ数: {len(failed_after)}")
    
    for doc in failed_after:
        data = doc.to_dict()
        print(f"失敗ジョブID: {doc.id}, エラーメッセージ: {data.get('error_message', 'なし')}")
    
    # エラーによりジョブステータスがfailedに変更されていることを確認
    assert len(failed_after) == 2  # 両方のジョブが失敗した状態になるはず
    
    # エラーメッセージが設定されていることを確認
    for job in failed_after:
        job_data = job.to_dict()
        assert "error_message" in job_data
        assert "バッチジョブ作成エラー" in job_data["error_message"]

# オプション：実際のBatchジョブを作成するテスト（普段はスキップ）
@pytest.mark.skip(reason="実際のBatchジョブを作成するため通常はスキップ")
def test_process_next_job_with_real_batch_job(setup_environment, setup_test_data):
    """モックなしで実際のBatchジョブを作成するテスト"""
    # テストデータをセットアップ - 待ち行列に1つのジョブを用意
    setup_test_data({'queued': 1, 'processing': 0, 'completed': 0, 'failed': 0, 'canceled': 0})
    
    # モックなしでprocess_next_job関数を実行
    process_next_job()
    
    # Firestoreのドキュメントを検証
    db = initialize_firestore()
    collection_name = os.environ.get('WHISPER_JOBS_COLLECTION', 'test_whisper_jobs')
    
    # ジョブのステータスが処理中に変更されていることを確認
    processing_jobs = list(db.collection(collection_name)
                          .where("status", "==", "processing")
                          .stream())
    
    assert len(processing_jobs) == 1
    
    # 実際にジョブが処理されている場合、process_started_atが設定されているはず
    job_data = processing_jobs[0].to_dict()
    assert "process_started_at" in job_data
    # 実行時間をチェックできる
    if "process_started_at" in job_data and job_data["process_started_at"]:
        start_time = job_data["process_started_at"]
        assert isinstance(start_time, datetime)
        # 現在時刻と大きく離れていないことを確認（5分以内）
        assert datetime.now() - start_time < timedelta(minutes=5)
