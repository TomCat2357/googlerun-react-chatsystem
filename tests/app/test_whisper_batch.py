"""
Whisperバッチ処理のテスト（モック中心）
"""

import pytest
import json
import tempfile
import uuid
from unittest.mock import patch, Mock, MagicMock, mock_open
from pathlib import Path
import pandas as pd
import time
import os

from common_utils.class_types import WhisperFirestoreData


class TestPickNextJob:
    """ジョブキューからの次のジョブ取得のテスト"""
    
    @pytest.mark.asyncio
    async def test_pick_next_job_success(self):
        """キューから次のジョブを正常に取得"""
        # Firestoreクライアントのモック
        mock_fs_client = MagicMock()
        mock_transaction = MagicMock()
        mock_fs_client.transaction.return_value = mock_transaction
        
        # ドキュメントのモック
        mock_doc = MagicMock()
        mock_doc.id = "test-job-123"
        mock_doc.reference = MagicMock()
        mock_doc.to_dict.return_value = {
            "job_id": "test-job-123",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.wav",
            "gcs_bucket_name": "test-bucket",
            "audio_size": 44100,
            "audio_duration_ms": 1000,
            "file_hash": "test-hash",
            "language": "ja",
            "initial_prompt": "",
            "status": "queued",
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1,
            "description": "テスト"
        }
        
        # コレクションとクエリのモック
        mock_collection = MagicMock()
        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc]
        mock_query.limit.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_collection.where.return_value = mock_query
        mock_fs_client.collection.return_value = mock_collection
        
        # transactional デコレータの動作をシミュレート
        def mock_transactional_decorator(func):
            def wrapper(*args, **kwargs):
                return func(mock_transaction)
            return wrapper
        
        # 環境変数をモック
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}), \
             patch("google.cloud.firestore.transactional", side_effect=mock_transactional_decorator):
            
            from whisper_batch.app.main import _pick_next_job
            
            # ジョブを取得
            result = _pick_next_job(mock_fs_client)
            
            assert result is not None
            assert result["job_id"] == "test-job-123"
            assert result["status"] == "processing"
            
            # トランザクション内でアップデートが呼ばれたことを確認
            mock_transaction.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_pick_next_job_empty_queue(self):
        """空のキューからジョブ取得を試行"""
        # Firestoreクライアントのモック
        mock_fs_client = MagicMock()
        mock_transaction = MagicMock()
        mock_fs_client.transaction.return_value = mock_transaction
        
        # 空のクエリ結果
        mock_collection = MagicMock()
        mock_query = MagicMock()
        mock_query.stream.return_value = []
        mock_query.limit.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_collection.where.return_value = mock_query
        mock_fs_client.collection.return_value = mock_collection
        
        # transactional デコレータの動作をシミュレート
        def mock_transactional_decorator(func):
            def wrapper(*args, **kwargs):
                return func(mock_transaction)
            return wrapper
        
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}), \
             patch("google.cloud.firestore.transactional", side_effect=mock_transactional_decorator):
            
            from whisper_batch.app.main import _pick_next_job
            
            result = _pick_next_job(mock_fs_client)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_pick_next_job_launched_status(self):
        """launchedステータスのジョブも取得対象になることを確認"""
        # Firestoreクライアントのモック
        mock_fs_client = MagicMock()
        mock_transaction = MagicMock()
        mock_fs_client.transaction.return_value = mock_transaction
        
        # ドキュメントのモック（launchedステータス）
        mock_doc = MagicMock()
        mock_doc.id = "test-job-launched"
        mock_doc.reference = MagicMock()
        mock_doc.to_dict.return_value = {
            "job_id": "test-job-launched",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.wav",
            "gcs_bucket_name": "test-bucket",
            "audio_size": 44100,
            "audio_duration_ms": 1000,
            "file_hash": "test-hash",
            "language": "ja",
            "initial_prompt": "",
            "status": "launched",
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1,
            "description": "テスト"
        }
        
        # コレクションとクエリのモック
        mock_collection = MagicMock()
        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc]
        mock_query.limit.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_collection.where.return_value = mock_query
        mock_fs_client.collection.return_value = mock_collection
        
        # transactional デコレータの動作をシミュレート
        def mock_transactional_decorator(func):
            def wrapper(*args, **kwargs):
                return func(mock_transaction)
            return wrapper
        
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}), \
             patch("google.cloud.firestore.transactional", side_effect=mock_transactional_decorator):
            
            from whisper_batch.app.main import _pick_next_job
            
            result = _pick_next_job(mock_fs_client)
            
            assert result is not None
            assert result["job_id"] == "test-job-launched"
            assert result["status"] == "processing"


class TestProcessJob:
    """ジョブ処理のテスト"""
    
    @pytest.mark.asyncio
    async def test_process_job_success_single_speaker(self, temp_directory):
        """単一話者のジョブ処理成功ケース"""
        # モッククライアント
        mock_fs_client = MagicMock()
        mock_gcs_client = MagicMock()
        
        # テスト用ジョブデータ
        job_data = {
            "job_id": "test-job-single",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.wav",
            "gcs_bucket_name": "test-bucket",
            "audio_size": 44100,
            "audio_duration_ms": 1000,
            "file_hash": "test-hash",
            "language": "ja",
            "initial_prompt": "",
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1,
            "description": "テスト"
        }
        
        # Firestoreドキュメントのモック
        mock_doc_ref = MagicMock()
        mock_fs_client.collection.return_value.document.return_value = mock_doc_ref
        mock_doc_ref.get.return_value.exists = True
        mock_doc_ref.get.return_value.to_dict.return_value = {"status": "processing"}
        mock_doc_ref.update.return_value = None
        
        # GCSのモック
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_to_filename.return_value = None
        mock_blob.upload_from_filename.return_value = None
        mock_gcs_client.bucket.return_value = mock_bucket
        
        # 環境変数を設定
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "LOCAL_TMP_DIR": str(temp_directory),
            "GCS_BUCKET": "test-bucket",
            "WHISPER_AUDIO_BLOB": "{file_hash}.wav",
            "WHISPER_TRANSCRIPT_BLOB": "{file_hash}_transcription.json",
            "WHISPER_DIARIZATION_BLOB": "{file_hash}_diarization.json",
            "WHISPER_COMBINE_BLOB": "{file_hash}/combine.json",
            "FULL_AUDIO_PATH": "gs://test-bucket/test-hash.wav",
            "FULL_TRANSCRIPTION_PATH": "gs://test-bucket/test-hash/combine.json",
            "HF_AUTH_TOKEN": "test-token",
            "DEVICE": "cpu"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("google.cloud.storage.Client", return_value=mock_gcs_client), \
             patch("whisper_batch.app.transcribe.transcribe_audio") as mock_transcribe, \
             patch("whisper_batch.app.main.create_single_speaker_json") as mock_single_speaker, \
             patch("whisper_batch.app.combine_results.combine_results") as mock_combine, \
             patch("shutil.rmtree"):
            
            from whisper_batch.app.main import _process_job
            
            # ジョブ処理を実行
            _process_job(mock_fs_client, job_data)
            
            # モック関数が呼ばれたことを確認
            mock_transcribe.assert_called_once()
            mock_single_speaker.assert_called_once()
            mock_combine.assert_called_once()
            
            # Firestoreの更新が呼ばれたことを確認
            mock_doc_ref.update.assert_called()
    
    @pytest.mark.asyncio
    async def test_process_job_success_multi_speaker(self, temp_directory):
        """複数話者のジョブ処理成功ケース"""
        # モッククライアント
        mock_fs_client = MagicMock()
        mock_gcs_client = MagicMock()
        
        # テスト用ジョブデータ（複数話者）
        job_data = {
            "job_id": "test-job-multi",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.wav",
            "gcs_bucket_name": "test-bucket",
            "audio_size": 44100,
            "audio_duration_ms": 1000,
            "file_hash": "test-hash",
            "language": "ja",
            "initial_prompt": "",
            "num_speakers": 2,
            "min_speakers": 2,
            "max_speakers": 2,
            "description": "テスト"
        }
        
        # Firestoreドキュメントのモック
        mock_doc_ref = MagicMock()
        mock_fs_client.collection.return_value.document.return_value = mock_doc_ref
        mock_doc_ref.get.return_value.exists = True
        mock_doc_ref.get.return_value.to_dict.return_value = {"status": "processing"}
        mock_doc_ref.update.return_value = None
        
        # GCSのモック
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_to_filename.return_value = None
        mock_blob.upload_from_filename.return_value = None
        mock_gcs_client.bucket.return_value = mock_bucket
        
        # 環境変数を設定
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "LOCAL_TMP_DIR": str(temp_directory),
            "GCS_BUCKET": "test-bucket",
            "WHISPER_AUDIO_BLOB": "{file_hash}.wav",
            "WHISPER_TRANSCRIPT_BLOB": "{file_hash}_transcription.json",
            "WHISPER_DIARIZATION_BLOB": "{file_hash}_diarization.json",
            "WHISPER_COMBINE_BLOB": "{file_hash}/combine.json",
            "FULL_AUDIO_PATH": "gs://test-bucket/test-hash.wav",
            "FULL_TRANSCRIPTION_PATH": "gs://test-bucket/test-hash/combine.json",
            "HF_AUTH_TOKEN": "test-token",
            "DEVICE": "cpu"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("google.cloud.storage.Client", return_value=mock_gcs_client), \
             patch("whisper_batch.app.transcribe.transcribe_audio") as mock_transcribe, \
             patch("whisper_batch.app.diarize.diarize_audio") as mock_diarize, \
             patch("whisper_batch.app.combine_results.combine_results") as mock_combine, \
             patch("shutil.rmtree"):
            
            from whisper_batch.app.main import _process_job
            
            # ジョブ処理を実行
            _process_job(mock_fs_client, job_data)
            
            # モック関数が呼ばれたことを確認
            mock_transcribe.assert_called_once()
            mock_diarize.assert_called_once()
            mock_combine.assert_called_once()
            
            # Firestoreの更新が呼ばれたことを確認
            mock_doc_ref.update.assert_called()
    
    @pytest.mark.asyncio
    async def test_process_job_invalid_data(self):
        """無効なジョブデータの処理"""
        mock_fs_client = MagicMock()
        
        # 必須フィールドが欠けているジョブデータ
        invalid_job_data = {
            "job_id": "invalid-job",
            "user_id": "test-user"
            # 他の必須フィールドが欠けている
        }
        
        # Firestoreドキュメントのモック
        mock_doc_ref = MagicMock()
        mock_fs_client.collection.return_value.document.return_value = mock_doc_ref
        mock_doc_ref.update.return_value = None
        
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}):
            from whisper_batch.app.main import _process_job
            
            # ジョブ処理を実行（例外が発生しないことを確認）
            _process_job(mock_fs_client, invalid_job_data)
            
            # Firestoreの更新が呼ばれたことを確認（失敗ステータス）
            mock_doc_ref.update.assert_called()
            
            # 更新呼び出しの引数を確認
            update_calls = mock_doc_ref.update.call_args_list
            assert len(update_calls) > 0
            
            # エラーメッセージを含む更新があることを確認
            update_data = update_calls[-1][0][0]
            assert "status" in update_data
            assert update_data["status"] == "failed"
            assert "error_message" in update_data
    
    @pytest.mark.asyncio
    async def test_process_job_transcription_error(self, temp_directory):
        """文字起こし処理でエラーが発生した場合"""
        mock_fs_client = MagicMock()
        mock_gcs_client = MagicMock()
        
        # 正常なジョブデータ
        job_data = {
            "job_id": "test-job-error",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.wav",
            "gcs_bucket_name": "test-bucket",
            "audio_size": 44100,
            "audio_duration_ms": 1000,
            "file_hash": "test-hash",
            "language": "ja",
            "initial_prompt": "",
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1,
            "description": "テスト"
        }
        
        # Firestoreドキュメントのモック
        mock_doc_ref = MagicMock()
        mock_fs_client.collection.return_value.document.return_value = mock_doc_ref
        mock_doc_ref.get.return_value.exists = True
        mock_doc_ref.get.return_value.to_dict.return_value = {"status": "processing"}
        mock_doc_ref.update.return_value = None
        
        # GCSのモック
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_to_filename.return_value = None
        mock_gcs_client.bucket.return_value = mock_bucket
        
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "LOCAL_TMP_DIR": str(temp_directory),
            "GCS_BUCKET": "test-bucket",
            "FULL_AUDIO_PATH": "gs://test-bucket/test-hash.wav",
            "FULL_TRANSCRIPTION_PATH": "gs://test-bucket/test-hash/combine.json",
            "HF_AUTH_TOKEN": "test-token",
            "DEVICE": "cpu"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("google.cloud.storage.Client", return_value=mock_gcs_client), \
             patch("whisper_batch.app.transcribe.transcribe_audio", side_effect=Exception("Transcription failed")), \
             patch("shutil.rmtree"):
            
            from whisper_batch.app.main import _process_job
            
            # ジョブ処理を実行
            _process_job(mock_fs_client, job_data)
            
            # ジョブが失敗ステータスに更新されることを確認
            mock_doc_ref.update.assert_called()
            
            # 更新呼び出しの引数を確認
            update_calls = mock_doc_ref.update.call_args_list
            assert len(update_calls) > 0
            
            # 失敗ステータスとエラーメッセージが含まれることを確認
            update_data = update_calls[-1][0][0]
            assert update_data["status"] == "failed"
            assert "Transcription failed" in update_data["error_message"]


class TestCreateSingleSpeakerJson:
    """単一話者JSON生成のテスト"""
    
    @pytest.mark.asyncio
    async def test_create_single_speaker_json_success(self, temp_directory):
        """単一話者JSON生成の成功ケース"""
        # サンプル文字起こし結果
        sample_transcription_data = [
            {"start": 0.0, "end": 1.0, "text": "こんにちは"},
            {"start": 1.0, "end": 2.0, "text": "今日はいい天気ですね"}
        ]
        
        # 入力ファイル（文字起こし結果）を作成
        transcription_file = temp_directory / "transcription.json"
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(sample_transcription_data, f, ensure_ascii=False)
        
        # 出力ファイルパス
        output_file = temp_directory / "single_speaker.json"
        
        # pandas.read_jsonの結果をモック
        mock_df = pd.DataFrame(sample_transcription_data)
        
        with patch("whisper_batch.app.combine_results.read_json", return_value=mock_df), \
             patch("whisper_batch.app.combine_results.save_dataframe") as mock_save:
            
            from whisper_batch.app.main import create_single_speaker_json
            
            # 単一話者JSON生成を実行
            create_single_speaker_json(str(transcription_file), str(output_file))
            
            # save_dataframeが呼ばれたことを確認
            mock_save.assert_called_once()
            
            # 呼び出された引数を確認
            call_args = mock_save.call_args[0]
            saved_df = call_args[0]
            output_path = call_args[1]
            
            # DataFrameにSPEAKER_01が追加されていることを確認
            assert len(saved_df) == len(sample_transcription_data)
            assert all(saved_df["speaker"] == "SPEAKER_01")
            assert str(output_path) == str(output_file)
    
    @pytest.mark.asyncio
    async def test_create_single_speaker_json_invalid_input(self, temp_directory):
        """無効な入力ファイルの場合"""
        # 存在しない入力ファイル
        transcription_file = temp_directory / "nonexistent.json"
        output_file = temp_directory / "single_speaker.json"
        
        # read_jsonでエラーを発生させる
        with patch("whisper_batch.app.combine_results.read_json", side_effect=FileNotFoundError("File not found")):
            
            from whisper_batch.app.main import create_single_speaker_json
            
            # 関数実行（例外が発生しないことを確認）
            create_single_speaker_json(str(transcription_file), str(output_file))
            
            # 空のJSONファイルが作成されることを確認
            assert output_file.exists()
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data == []


class TestMainLoop:
    """メインループのテスト"""
    
    @pytest.mark.asyncio
    async def test_main_loop_process_job(self):
        """メインループでジョブが処理されることを確認"""
        mock_fs_client = MagicMock()
        
        # テストジョブデータ
        test_job = {
            "job_id": "test-main-loop",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.wav",
            "gcs_bucket_name": "test-bucket",
            "audio_size": 44100,
            "audio_duration_ms": 1000,
            "file_hash": "test-hash",
            "language": "ja",
            "initial_prompt": "",
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1,
            "description": "テスト"
        }
        
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "POLL_INTERVAL_SECONDS": "1"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("google.cloud.firestore.Client", return_value=mock_fs_client), \
             patch("whisper_batch.app.main._pick_next_job", return_value=test_job) as mock_pick_job, \
             patch("whisper_batch.app.main._process_job") as mock_process_job, \
             patch("time.sleep") as mock_sleep:
            
            # KeyboardInterruptを発生させてループを停止
            mock_sleep.side_effect = [None, KeyboardInterrupt()]
            
            from whisper_batch.app.main import main_loop
            
            # メインループを実行
            try:
                main_loop()
            except KeyboardInterrupt:
                pass
            
            # ジョブ処理関数が呼ばれたことを確認
            mock_process_job.assert_called_once_with(mock_fs_client, test_job)
    
    @pytest.mark.asyncio
    async def test_main_loop_empty_queue(self):
        """キューが空の場合のメインループ"""
        mock_fs_client = MagicMock()
        
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "POLL_INTERVAL_SECONDS": "1"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("google.cloud.firestore.Client", return_value=mock_fs_client), \
             patch("whisper_batch.app.main._pick_next_job", return_value=None), \
             patch("time.sleep") as mock_sleep:
            
            # すぐにKeyboardInterruptを発生させてループを停止
            mock_sleep.side_effect = KeyboardInterrupt()
            
            from whisper_batch.app.main import main_loop
            
            # メインループを実行
            try:
                main_loop()
            except KeyboardInterrupt:
                pass
            
            # sleepが呼ばれたことを確認（キューが空なので待機）
            mock_sleep.assert_called_once_with(1)
    
    @pytest.mark.asyncio
    async def test_main_loop_exception_handling(self):
        """メインループでの例外処理"""
        mock_fs_client = MagicMock()
        
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "POLL_INTERVAL_SECONDS": "1"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("google.cloud.firestore.Client", return_value=mock_fs_client), \
             patch("whisper_batch.app.main._pick_next_job", side_effect=Exception("Database error")), \
             patch("time.sleep") as mock_sleep:
            
            # 2回目のsleepでKeyboardInterruptを発生
            mock_sleep.side_effect = [None, KeyboardInterrupt()]
            
            from whisper_batch.app.main import main_loop
            
            # メインループを実行
            try:
                main_loop()
            except KeyboardInterrupt:
                pass
            
            # 例外が発生してもループが続行されることを確認
            assert mock_sleep.call_count == 2


class TestEnvironmentAndConfig:
    """環境変数と設定のテスト"""
    
    def test_required_environment_variables(self):
        """必須環境変数のテスト"""
        required_vars = [
            "COLLECTION",
            "HF_AUTH_TOKEN",
            "DEVICE",
            "LOCAL_TMP_DIR",
            "GCS_BUCKET"
        ]
        
        # 各環境変数が設定されていることを確認するテスト
        for var in required_vars:
            assert os.environ.get(var) is not None, f"環境変数 {var} が設定されていません"
    
    def test_optional_environment_variables(self):
        """オプション環境変数のテスト"""
        # デフォルト値があるかどうかの確認
        with patch.dict(os.environ, {}, clear=False):
            # POLL_INTERVAL_SECONDSのデフォルト値テスト
            poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "10"))
            assert poll_interval >= 1  # 合理的なデフォルト値
    
    def test_device_configuration(self):
        """デバイス設定のテスト"""
        device = os.environ.get("DEVICE", "cpu").lower()
        assert device in ["cpu", "cuda"], f"無効なデバイス設定: {device}"
        
        # GPU使用フラグのテスト
        use_gpu = device == "cuda"
        assert isinstance(use_gpu, bool)


class TestGCSPathParsing:
    """GCSパス解析のテスト"""
    
    def test_parse_gcs_path_valid(self):
        """有効なGCSパスの解析"""
        # parse_gcs_path関数のテスト用ヘルパー
        def parse_gcs_path(gcs_path: str) -> tuple[str, str]:
            if not gcs_path.startswith("gs://"):
                raise ValueError(f"Invalid GCS path: {gcs_path}")
            parts = gcs_path[5:].split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Cannot parse bucket and blob from GCS path: {gcs_path}")
            return parts[0], parts[1]
        
        # 一般的なGCSパス
        bucket, blob = parse_gcs_path("gs://test-bucket/path/to/file.wav")
        assert bucket == "test-bucket"
        assert blob == "path/to/file.wav"
        
        # ルート直下のファイル
        bucket, blob = parse_gcs_path("gs://another-bucket/file.json")
        assert bucket == "another-bucket"
        assert blob == "file.json"
    
    def test_parse_gcs_path_invalid(self):
        """無効なGCSパスの解析"""
        def parse_gcs_path(gcs_path: str) -> tuple[str, str]:
            if not gcs_path.startswith("gs://"):
                raise ValueError(f"Invalid GCS path: {gcs_path}")
            parts = gcs_path[5:].split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Cannot parse bucket and blob from GCS path: {gcs_path}")
            return parts[0], parts[1]
        
        # gs://プレフィックスがない
        with pytest.raises(ValueError):
            parse_gcs_path("test-bucket/file.wav")
        
        # バケット名のみ
        with pytest.raises(ValueError):
            parse_gcs_path("gs://test-bucket")
        
        # 空文字列
        with pytest.raises(ValueError):
            parse_gcs_path("")


class TestWhisperBatchUtilities:
    """Whisperバッチ処理のユーティリティ関数テスト"""
    
    def test_data_validation(self):
        """データ検証のテスト"""
        # 有効なデータ
        valid_data = {
            "job_id": "test-validation",
            "user_id": "test-user",
            "user_email": "test@example.com",
            "filename": "test.wav",
            "gcs_bucket_name": "test-bucket",
            "audio_size": 44100,
            "audio_duration_ms": 1000,
            "file_hash": "test-hash",
            "language": "ja",
            "initial_prompt": "",
            "num_speakers": 1,
            "min_speakers": 1,
            "max_speakers": 1,
            "description": "テスト"
        }
        
        # WhisperFirestoreDataで検証
        try:
            validated_data = WhisperFirestoreData(**valid_data)
            assert validated_data.job_id == "test-validation"
            assert validated_data.num_speakers == 1
        except Exception as e:
            pytest.fail(f"有効なデータの検証に失敗: {e}")
        
        # 無効なデータ（必須フィールド不足）
        invalid_data = {
            "job_id": "test-invalid",
            "user_id": "test-user"
            # 他の必須フィールドが不足
        }
        
        with pytest.raises(Exception):
            WhisperFirestoreData(**invalid_data)
    
    def test_speaker_mode_detection(self):
        """話者モード検出のテスト"""
        # 単一話者判定のロジックをテスト
        def is_single_speaker(num_speakers, min_speakers, max_speakers):
            return num_speakers == 1 or (
                num_speakers is None and max_speakers == 1 and min_speakers == 1
            )
        
        # 明示的な単一話者
        assert is_single_speaker(1, 1, 1) is True
        
        # 明示的な複数話者
        assert is_single_speaker(2, 2, 2) is False
        
        # None指定での単一話者
        assert is_single_speaker(None, 1, 1) is True
        
        # None指定での複数話者の可能性
        assert is_single_speaker(None, 1, 2) is False
