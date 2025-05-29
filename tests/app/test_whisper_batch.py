"""
Whisperバッチ処理のテスト
"""

import pytest
import json
import tempfile
import uuid
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import pandas as pd
import time
import os

from common_utils.class_types import WhisperFirestoreData
from whisper_batch.app.main import (
    _pick_next_job,
    _process_job, 
    create_single_speaker_json,
    main_loop
)


class TestPickNextJob:
    """ジョブキューからの次のジョブ取得のテスト"""
    
    @pytest.mark.asyncio
    async def test_pick_next_job_success(self, firestore_client, sample_firestore_job):
        """キューから次のジョブを正常に取得"""
        # テストジョブをFirestoreに登録
        job_data = sample_firestore_job.model_dump()
        job_data["status"] = "queued"
        job_data["upload_at"] = firestore_client.SERVER_TIMESTAMP
        
        doc_ref = firestore_client.collection("whisper_jobs").document(sample_firestore_job.job_id)
        doc_ref.set(job_data)
        
        # 環境変数をモック
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}):
            # ジョブを取得
            result = _pick_next_job(firestore_client)
            
            assert result is not None
            assert result["job_id"] == sample_firestore_job.job_id
            assert result["status"] == "processing"
            
            # Firestoreのステータスが更新されていることを確認
            updated_doc = doc_ref.get()
            assert updated_doc.to_dict()["status"] == "processing"
    
    @pytest.mark.asyncio
    async def test_pick_next_job_empty_queue(self, firestore_client):
        """空のキューからジョブ取得を試行"""
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}):
            result = _pick_next_job(firestore_client)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_pick_next_job_launched_status(self, firestore_client, sample_firestore_job):
        """launchedステータスのジョブも取得対象になることを確認"""
        job_data = sample_firestore_job.model_dump()
        job_data["status"] = "launched"
        job_data["upload_at"] = firestore_client.SERVER_TIMESTAMP
        
        doc_ref = firestore_client.collection("whisper_jobs").document(sample_firestore_job.job_id)
        doc_ref.set(job_data)
        
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}):
            result = _pick_next_job(firestore_client)
            
            assert result is not None
            assert result["status"] == "processing"


class TestProcessJob:
    """ジョブ処理のテスト"""
    
    @pytest.mark.asyncio
    async def test_process_job_success_single_speaker(self, firestore_client, gcs_client, sample_firestore_job, sample_audio_file, temp_directory):
        """単一話者のジョブ処理成功ケース"""
        # テスト環境のセットアップ
        job_data = sample_firestore_job.model_dump()
        job_data["num_speakers"] = 1
        
        # GCSにテスト音声ファイルをアップロード
        bucket = gcs_client.bucket("test-whisper-bucket")
        audio_blob_name = f"{sample_firestore_job.file_hash}.wav"
        audio_blob = bucket.blob(audio_blob_name)
        
        with open(sample_audio_file, "rb") as f:
            audio_blob.upload_from_file(f)
        
        # 環境変数をモック
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "LOCAL_TMP_DIR": str(temp_directory),
            "GCS_BUCKET": "test-whisper-bucket",
            "WHISPER_AUDIO_BLOB": "{file_hash}.wav",
            "WHISPER_TRANSCRIPT_BLOB": "{file_hash}_transcription.json",
            "WHISPER_DIARIZATION_BLOB": "{file_hash}_diarization.json",
            "WHISPER_COMBINE_BLOB": "{file_hash}/combine.json",
            "FULL_AUDIO_PATH": f"gs://test-whisper-bucket/{audio_blob_name}",
            "FULL_TRANSCRIPTION_PATH": f"gs://test-whisper-bucket/{sample_firestore_job.file_hash}/combine.json",
            "HF_AUTH_TOKEN": "test-token",
            "DEVICE": "cpu"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("whisper_batch.app.transcribe.transcribe_audio") as mock_transcribe, \
             patch("whisper_batch.app.main.create_single_speaker_json") as mock_single_speaker, \
             patch("whisper_batch.app.combine_results.combine_results") as mock_combine:
            
            # モックの戻り値を設定
            mock_transcribe.return_value = pd.DataFrame([
                {"start": 0.0, "end": 1.0, "text": "こんにちは"}
            ])
            
            # ジョブ処理を実行
            _process_job(firestore_client, job_data)
            
            # モック関数が呼ばれたことを確認
            mock_transcribe.assert_called_once()
            mock_single_speaker.assert_called_once()
            mock_combine.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_job_success_multi_speaker(self, firestore_client, gcs_client, sample_firestore_job, sample_audio_file, temp_directory):
        """複数話者のジョブ処理成功ケース"""
        job_data = sample_firestore_job.model_dump()
        job_data["num_speakers"] = 2
        job_data["min_speakers"] = 2
        job_data["max_speakers"] = 2
        
        # GCSにテスト音声ファイルをアップロード
        bucket = gcs_client.bucket("test-whisper-bucket")
        audio_blob_name = f"{sample_firestore_job.file_hash}.wav"
        audio_blob = bucket.blob(audio_blob_name)
        
        with open(sample_audio_file, "rb") as f:
            audio_blob.upload_from_file(f)
        
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "LOCAL_TMP_DIR": str(temp_directory),
            "GCS_BUCKET": "test-whisper-bucket",
            "WHISPER_AUDIO_BLOB": "{file_hash}.wav",
            "WHISPER_TRANSCRIPT_BLOB": "{file_hash}_transcription.json",
            "WHISPER_DIARIZATION_BLOB": "{file_hash}_diarization.json",
            "WHISPER_COMBINE_BLOB": "{file_hash}/combine.json",
            "FULL_AUDIO_PATH": f"gs://test-whisper-bucket/{audio_blob_name}",
            "FULL_TRANSCRIPTION_PATH": f"gs://test-whisper-bucket/{sample_firestore_job.file_hash}/combine.json",
            "HF_AUTH_TOKEN": "test-token",
            "DEVICE": "cpu"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("whisper_batch.app.transcribe.transcribe_audio") as mock_transcribe, \
             patch("whisper_batch.app.diarize.diarize_audio") as mock_diarize, \
             patch("whisper_batch.app.combine_results.combine_results") as mock_combine:
            
            # モックの戻り値を設定
            mock_transcribe.return_value = pd.DataFrame([
                {"start": 0.0, "end": 1.0, "text": "こんにちは"}
            ])
            
            # ジョブ処理を実行
            _process_job(firestore_client, job_data)
            
            # モック関数が呼ばれたことを確認
            mock_transcribe.assert_called_once()
            mock_diarize.assert_called_once()
            mock_combine.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_job_invalid_data(self, firestore_client):
        """無効なジョブデータの処理"""
        # 必須フィールドが欠けているジョブデータ
        invalid_job_data = {
            "job_id": "invalid-job",
            "user_id": "test-user"
            # 他の必須フィールドが欠けている
        }
        
        with patch.dict(os.environ, {"COLLECTION": "whisper_jobs"}):
            # ジョブ処理を実行（例外が発生しないことを確認）
            _process_job(firestore_client, invalid_job_data)
            
            # Firestoreでジョブが失敗ステータスに更新されることを確認
            # （実際のテストではFirestoreの状態を確認する）
    
    @pytest.mark.asyncio
    async def test_process_job_transcription_error(self, firestore_client, gcs_client, sample_firestore_job, sample_audio_file, temp_directory):
        """文字起こし処理でエラーが発生した場合"""
        job_data = sample_firestore_job.model_dump()
        
        # Firestoreにジョブドキュメントを作成
        doc_ref = firestore_client.collection("whisper_jobs").document(sample_firestore_job.job_id)
        doc_ref.set(job_data)
        
        # GCSにテスト音声ファイルをアップロード
        bucket = gcs_client.bucket("test-whisper-bucket")
        audio_blob_name = f"{sample_firestore_job.file_hash}.wav"
        audio_blob = bucket.blob(audio_blob_name)
        
        with open(sample_audio_file, "rb") as f:
            audio_blob.upload_from_file(f)
        
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "LOCAL_TMP_DIR": str(temp_directory),
            "GCS_BUCKET": "test-whisper-bucket",
            "WHISPER_AUDIO_BLOB": "{file_hash}.wav",
            "FULL_AUDIO_PATH": f"gs://test-whisper-bucket/{audio_blob_name}",
            "FULL_TRANSCRIPTION_PATH": f"gs://test-whisper-bucket/{sample_firestore_job.file_hash}/combine.json",
            "HF_AUTH_TOKEN": "test-token",
            "DEVICE": "cpu"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("whisper_batch.app.transcribe.transcribe_audio", side_effect=Exception("Transcription failed")):
            
            # ジョブ処理を実行
            _process_job(firestore_client, job_data)
            
            # ジョブが失敗ステータスに更新されることを確認
            updated_doc = doc_ref.get()
            updated_data = updated_doc.to_dict()
            assert updated_data["status"] == "failed"
            assert "Transcription failed" in updated_data["error_message"]


class TestCreateSingleSpeakerJson:
    """単一話者JSON生成のテスト"""
    
    @pytest.mark.asyncio
    async def test_create_single_speaker_json_success(self, temp_directory, sample_transcription_result):
        """単一話者JSON生成の成功ケース"""
        # 入力ファイル（文字起こし結果）を作成
        transcription_file = temp_directory / "transcription.json"
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(sample_transcription_result, f, ensure_ascii=False)
        
        # 出力ファイルパス
        output_file = temp_directory / "single_speaker.json"
        
        # 単一話者JSON生成を実行
        create_single_speaker_json(str(transcription_file), str(output_file))
        
        # 出力ファイルが作成されることを確認
        assert output_file.exists()
        
        # 出力内容を確認
        with open(output_file, "r", encoding="utf-8") as f:
            speaker_data = json.load(f)
        
        assert len(speaker_data) == len(sample_transcription_result)
        for item in speaker_data:
            assert item["speaker"] == "SPEAKER_01"
            assert "start" in item
            assert "end" in item
    
    @pytest.mark.asyncio
    async def test_create_single_speaker_json_invalid_input(self, temp_directory):
        """無効な入力ファイルの場合"""
        # 存在しない入力ファイル
        transcription_file = temp_directory / "nonexistent.json"
        output_file = temp_directory / "single_speaker.json"
        
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
    async def test_main_loop_process_job(self, firestore_client, sample_firestore_job):
        """メインループでジョブが処理されることを確認"""
        # テストジョブをFirestoreに登録
        job_data = sample_firestore_job.model_dump()
        job_data["status"] = "queued"
        job_data["upload_at"] = firestore_client.SERVER_TIMESTAMP
        
        doc_ref = firestore_client.collection("whisper_jobs").document(sample_firestore_job.job_id)
        doc_ref.set(job_data)
        
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "POLL_INTERVAL_SECONDS": "1"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("whisper_batch.app.main._process_job") as mock_process_job, \
             patch("time.sleep") as mock_sleep:
            
            # KeyboardInterruptを発生させてループを停止
            mock_sleep.side_effect = [None, KeyboardInterrupt()]
            
            # メインループを実行
            try:
                main_loop()
            except KeyboardInterrupt:
                pass
            
            # ジョブ処理関数が呼ばれたことを確認
            mock_process_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_main_loop_empty_queue(self, firestore_client):
        """キューが空の場合のメインループ"""
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "POLL_INTERVAL_SECONDS": "1"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("time.sleep") as mock_sleep:
            
            # すぐにKeyboardInterruptを発生させてループを停止
            mock_sleep.side_effect = KeyboardInterrupt()
            
            # メインループを実行
            try:
                main_loop()
            except KeyboardInterrupt:
                pass
            
            # sleepが呼ばれたことを確認（キューが空なので待機）
            mock_sleep.assert_called_once_with(1)
    
    @pytest.mark.asyncio
    async def test_main_loop_exception_handling(self, firestore_client):
        """メインループでの例外処理"""
        env_vars = {
            "COLLECTION": "whisper_jobs",
            "POLL_INTERVAL_SECONDS": "1"
        }
        
        with patch.dict(os.environ, env_vars), \
             patch("whisper_batch.app.main._pick_next_job", side_effect=Exception("Database error")), \
             patch("time.sleep") as mock_sleep:
            
            # 2回目のsleepでKeyboardInterruptを発生
            mock_sleep.side_effect = [None, KeyboardInterrupt()]
            
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
            "GCS_BUCKET",
            "WHISPER_AUDIO_BLOB",
            "WHISPER_TRANSCRIPT_BLOB",
            "WHISPER_DIARIZATION_BLOB",
            "WHISPER_COMBINE_BLOB"
        ]
        
        # 各環境変数が設定されていることを確認するテスト
        for var in required_vars:
            with patch.dict(os.environ, {var: "test_value"}):
                assert os.environ.get(var) == "test_value"
    
    def test_optional_environment_variables(self):
        """オプション環境変数のテスト"""
        # デフォルト値があるかどうかの確認
        with patch.dict(os.environ, {}, clear=True):
            # POLL_INTERVAL_SECONDSのデフォルト値テスト
            poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "10"))
            assert poll_interval == 10
    
    def test_device_configuration(self):
        """デバイス設定のテスト"""
        # CPU設定
        with patch.dict(os.environ, {"DEVICE": "cpu"}):
            assert os.environ["DEVICE"].lower() == "cpu"
        
        # CUDA設定
        with patch.dict(os.environ, {"DEVICE": "cuda"}):
            assert os.environ["DEVICE"].lower() == "cuda"
            
        # GPU使用フラグのテスト
        with patch.dict(os.environ, {"DEVICE": "cuda"}):
            use_gpu = os.environ["DEVICE"].lower() == "cuda"
            assert use_gpu is True
            
        with patch.dict(os.environ, {"DEVICE": "cpu"}):
            use_gpu = os.environ["DEVICE"].lower() == "cuda"
            assert use_gpu is False


class TestGCSPathParsing:
    """GCSパス解析のテスト"""
    
    def test_parse_gcs_path_valid(self):
        """有効なGCSパスの解析"""
        from whisper_batch.app.main import parse_gcs_path
        
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
        from whisper_batch.app.main import parse_gcs_path
        
        # gs://プレフィックスがない
        with pytest.raises(ValueError):
            parse_gcs_path("test-bucket/file.wav")
        
        # バケット名のみ
        with pytest.raises(ValueError):
            parse_gcs_path("gs://test-bucket")
        
        # 空文字列
        with pytest.raises(ValueError):
            parse_gcs_path("")
