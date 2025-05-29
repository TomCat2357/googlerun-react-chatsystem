"""
Whisper文字起こし機能のテスト
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import pandas as pd
import numpy as np
from pydub import AudioSegment

from whisper_batch.app.transcribe import (
    _get_whisper_model,
    transcribe_audio,
    is_gcs_path,
    save_dataframe_to_local,
    save_dataframe_to_gcs,
    save_dataframe
)


class TestGetWhisperModel:
    """Whisperモデルのグローバルインスタンスのテスト"""
    
    @pytest.mark.asyncio
    async def test_get_whisper_model_first_call(self):
        """初回呼び出し時のモデル初期化"""
        with patch("whisper_batch.app.transcribe._GLOBAL_WHISPER_MODEL", None), \
             patch("whisper_batch.app.transcribe.WhisperModel") as mock_whisper_model, \
             patch("torch.cuda.is_available", return_value=False):
            
            mock_model_instance = Mock()
            mock_whisper_model.return_value = mock_model_instance
            
            # 初回呼び出し
            result = _get_whisper_model(device="cpu")
            
            # モデルが初期化されたことを確認
            mock_whisper_model.assert_called_once_with("large", device="cpu")
            assert result == mock_model_instance
    
    @pytest.mark.asyncio
    async def test_get_whisper_model_cached(self):
        """2回目以降の呼び出し（キャッシュされたモデルの使用）"""
        mock_cached_model = Mock()
        
        with patch("whisper_batch.app.transcribe._GLOBAL_WHISPER_MODEL", mock_cached_model), \
             patch("whisper_batch.app.transcribe.WhisperModel") as mock_whisper_model:
            
            # 2回目の呼び出し
            result = _get_whisper_model(device="cpu")
            
            # モデルが再初期化されないことを確認
            mock_whisper_model.assert_not_called()
            assert result == mock_cached_model
    
    @pytest.mark.asyncio
    async def test_get_whisper_model_cuda_fallback(self):
        """CUDA要求時にCUDAが利用不可の場合のCPUフォールバック"""
        with patch("whisper_batch.app.transcribe._GLOBAL_WHISPER_MODEL", None), \
             patch("whisper_batch.app.transcribe.WhisperModel") as mock_whisper_model, \
             patch("torch.cuda.is_available", return_value=False):
            
            mock_model_instance = Mock()
            mock_whisper_model.return_value = mock_model_instance
            
            # CUDAを要求するがCPUにフォールバック
            result = _get_whisper_model(device="cuda")
            
            # CPUデバイスでモデルが初期化されることを確認
            mock_whisper_model.assert_called_once_with("large", device="cpu")
    
    @pytest.mark.asyncio
    async def test_get_whisper_model_cuda_available(self):
        """CUDAが利用可能な場合"""
        with patch("whisper_batch.app.transcribe._GLOBAL_WHISPER_MODEL", None), \
             patch("whisper_batch.app.transcribe.WhisperModel") as mock_whisper_model, \
             patch("torch.cuda.is_available", return_value=True):
            
            mock_model_instance = Mock()
            mock_whisper_model.return_value = mock_model_instance
            
            # CUDAでモデル初期化
            result = _get_whisper_model(device="cuda")
            
            # CUDAデバイスでモデルが初期化されることを確認
            mock_whisper_model.assert_called_once_with("large", device="cuda")


class TestTranscribeAudio:
    """音声文字起こし機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_success(self, sample_audio_file, temp_directory):
        """文字起こしの成功ケース"""
        output_file = temp_directory / "transcription_result.json"
        
        # モックセグメント
        mock_segments = [
            Mock(start=0.0, end=1.0, text="こんにちは"),
            Mock(start=1.0, end=2.0, text="世界")
        ]
        
        # モック情報
        mock_info = Mock()
        mock_info.language = "ja"
        
        # Whisperモデルのモック
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe") as mock_save:
            
            # 文字起こし実行
            result = transcribe_audio(
                sample_audio_file,
                str(output_file),
                device="cpu",
                job_id="test-job-123",
                language="ja",
                initial_prompt="テストプロンプト"
            )
            
            # Whisperモデルが正しいパラメータで呼ばれることを確認
            mock_model.transcribe.assert_called_once_with(
                sample_audio_file,
                beam_size=5,
                language="ja",
                initial_prompt="テストプロンプト"
            )
            
            # 結果の確認
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 2
            assert result.iloc[0]["text"] == "こんにちは"
            assert result.iloc[1]["text"] == "世界"
            
            # 保存関数が呼ばれることを確認
            mock_save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_auto_language(self, sample_audio_file, temp_directory):
        """言語自動検出の場合"""
        output_file = temp_directory / "transcription_result.json"
        
        mock_segments = [Mock(start=0.0, end=1.0, text="hello")]
        mock_info = Mock()
        mock_info.language = "en"
        
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe"):
            
            # 言語を"auto"で指定
            transcribe_audio(
                sample_audio_file,
                str(output_file),
                device="cpu",
                language="auto"
            )
            
            # languageパラメータがNoneで渡されることを確認
            mock_model.transcribe.assert_called_once_with(
                sample_audio_file,
                beam_size=5,
                language=None
            )
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_empty_prompt(self, sample_audio_file, temp_directory):
        """空のプロンプトの場合"""
        output_file = temp_directory / "transcription_result.json"
        
        mock_segments = [Mock(start=0.0, end=1.0, text="test")]
        mock_info = Mock()
        
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe"):
            
            # 空のプロンプトを指定
            transcribe_audio(
                sample_audio_file,
                str(output_file),
                device="cpu",
                initial_prompt=""
            )
            
            # initial_promptパラメータが渡されないことを確認
            args, kwargs = mock_model.transcribe.call_args
            assert "initial_prompt" not in kwargs
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_with_job_id(self, sample_audio_file, temp_directory):
        """ジョブIDを含む場合のログ出力確認"""
        output_file = temp_directory / "transcription_result.json"
        
        mock_segments = [Mock(start=0.0, end=1.0, text="test")]
        mock_info = Mock()
        mock_info.language = "ja"
        
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe"), \
             patch("whisper_batch.app.transcribe.logger") as mock_logger:
            
            # ジョブID付きで文字起こし
            transcribe_audio(
                sample_audio_file,
                str(output_file),
                device="cpu",
                job_id="test-job-456"
            )
            
            # ログにジョブIDが含まれることを確認
            log_calls = [call.args[0] for call in mock_logger.info.call_args_list]
            assert any("JOB test-job-456" in log for log in log_calls)


class TestGCSPathHandling:
    """GCSパス判定のテスト"""
    
    def test_is_gcs_path_true(self):
        """GCSパスの正しい判定"""
        assert is_gcs_path("gs://bucket/path/to/file.json") is True
        assert is_gcs_path("gs://my-bucket/audio.wav") is True
    
    def test_is_gcs_path_false(self):
        """非GCSパスの正しい判定"""
        assert is_gcs_path("/local/path/to/file.json") is False
        assert is_gcs_path("./relative/path.wav") is False
        assert is_gcs_path("http://example.com/file.mp3") is False
        assert is_gcs_path("s3://bucket/file.txt") is False


class TestSaveDataframe:
    """データフレーム保存機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_save_dataframe_to_local(self, temp_directory):
        """ローカルファイルへの保存"""
        df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "text": "こんにちは"},
            {"start": 1.0, "end": 2.0, "text": "世界"}
        ])
        
        output_file = temp_directory / "test_output.json"
        
        # ローカル保存の実行
        save_dataframe_to_local(df, str(output_file))
        
        # ファイルが作成されることを確認
        assert output_file.exists()
        
        # 内容の確認
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert len(data) == 2
        assert data[0]["text"] == "こんにちは"
        assert data[1]["text"] == "世界"
    
    @pytest.mark.asyncio
    async def test_save_dataframe_to_gcs(self):
        """GCSへの保存"""
        df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "text": "test"}
        ])
        
        gcs_uri = "gs://test-bucket/transcription/result.json"
        
        with patch("google.cloud.storage.Client") as mock_storage:
            # GCSクライアントのモック
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_storage.return_value.bucket.return_value = mock_bucket
            
            # GCS保存の実行
            save_dataframe_to_gcs(df, gcs_uri)
            
            # 正しいバケットとブロブが使用されることを確認
            mock_storage.return_value.bucket.assert_called_once_with("test-bucket")
            mock_bucket.blob.assert_called_once_with("transcription/result.json")
            
            # アップロードが実行されることを確認
            mock_blob.upload_from_string.assert_called_once()
            
            # アップロード内容の確認
            upload_call = mock_blob.upload_from_string.call_args
            uploaded_content = upload_call[0][0]
            assert '"text": "test"' in uploaded_content
    
    @pytest.mark.asyncio
    async def test_save_dataframe_local_path(self, temp_directory):
        """save_dataframe関数でローカルパスを使用"""
        df = pd.DataFrame([{"start": 0.0, "end": 1.0, "text": "local test"}])
        output_file = temp_directory / "local_test.json"
        
        with patch("whisper_batch.app.transcribe.save_dataframe_to_local") as mock_local_save:
            save_dataframe(df, str(output_file))
            mock_local_save.assert_called_once_with(df, str(output_file))
    
    @pytest.mark.asyncio
    async def test_save_dataframe_gcs_path(self):
        """save_dataframe関数でGCSパスを使用"""
        df = pd.DataFrame([{"start": 0.0, "end": 1.0, "text": "gcs test"}])
        gcs_path = "gs://test-bucket/test.json"
        
        with patch("whisper_batch.app.transcribe.save_dataframe_to_gcs") as mock_gcs_save:
            save_dataframe(df, gcs_path)
            mock_gcs_save.assert_called_once_with(df, gcs_path)


class TestTranscriptionDataProcessing:
    """文字起こしデータ処理のテスト"""
    
    @pytest.mark.asyncio
    async def test_segments_to_dataframe_conversion(self):
        """WhisperセグメントからDataFrameへの変換"""
        # モックセグメント（Whisperの実際の出力を模擬）
        mock_segments = [
            Mock(start=0.0, end=1.5, text="最初のセグメント"),
            Mock(start=1.5, end=3.0, text="二番目のセグメント"),
            Mock(start=3.0, end=4.2, text="最後のセグメント")
        ]
        
        mock_info = Mock()
        mock_info.language = "ja"
        
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe") as mock_save:
            
            result = transcribe_audio(
                "dummy_audio.wav",
                "dummy_output.json",
                device="cpu"
            )
            
            # DataFrameの構造確認
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 3
            assert list(result.columns) == ["start", "end", "text"]
            
            # 各行のデータ確認
            assert result.iloc[0]["start"] == 0.0
            assert result.iloc[0]["end"] == 1.5
            assert result.iloc[0]["text"] == "最初のセグメント"
            
            assert result.iloc[2]["start"] == 3.0
            assert result.iloc[2]["end"] == 4.2
            assert result.iloc[2]["text"] == "最後のセグメント"
    
    @pytest.mark.asyncio
    async def test_empty_segments_handling(self):
        """空のセグメントの処理"""
        mock_segments = []  # 空のセグメントリスト
        mock_info = Mock()
        mock_info.language = "en"
        
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe"):
            
            result = transcribe_audio(
                "silent_audio.wav",
                "empty_output.json",
                device="cpu"
            )
            
            # 空のDataFrameが返されることを確認
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 0
            assert list(result.columns) == ["start", "end", "text"]
    
    @pytest.mark.asyncio
    async def test_special_characters_in_text(self):
        """特殊文字を含むテキストの処理"""
        mock_segments = [
            Mock(start=0.0, end=1.0, text="こんにちは！"),
            Mock(start=1.0, end=2.0, text="「質問です」"),
            Mock(start=2.0, end=3.0, text="回答：はい。"),
            Mock(start=3.0, end=4.0, text="100%確実です"),
            Mock(start=4.0, end=5.0, text="E=mc²")
        ]
        
        mock_info = Mock()
        mock_info.language = "ja"
        
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe"):
            
            result = transcribe_audio(
                "special_chars_audio.wav",
                "special_output.json",
                device="cpu"
            )
            
            # 特殊文字がそのまま保持されることを確認
            texts = result["text"].tolist()
            assert "こんにちは！" in texts
            assert "「質問です」" in texts
            assert "回答：はい。" in texts
            assert "100%確実です" in texts
            assert "E=mc²" in texts


class TestErrorHandling:
    """エラーハンドリングのテスト"""
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_model_error(self, sample_audio_file, temp_directory):
        """Whisperモデルでエラーが発生した場合"""
        output_file = temp_directory / "error_output.json"
        
        mock_model = Mock()
        mock_model.transcribe.side_effect = Exception("Model processing error")
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model):
            # エラーが再発生することを確認
            with pytest.raises(Exception, match="Model processing error"):
                transcribe_audio(
                    sample_audio_file,
                    str(output_file),
                    device="cpu"
                )
    
    @pytest.mark.asyncio
    async def test_save_dataframe_gcs_error(self):
        """GCS保存でエラーが発生した場合"""
        df = pd.DataFrame([{"start": 0.0, "end": 1.0, "text": "test"}])
        gcs_uri = "gs://invalid-bucket/file.json"
        
        with patch("google.cloud.storage.Client") as mock_storage:
            # GCSクライアントでエラーを発生させる
            mock_storage.side_effect = Exception("GCS connection error")
            
            # エラーが再発生することを確認
            with pytest.raises(Exception, match="GCS connection error"):
                save_dataframe_to_gcs(df, gcs_uri)
    
    @pytest.mark.asyncio
    async def test_save_dataframe_local_permission_error(self, temp_directory):
        """ローカルファイル保存でアクセス権限エラーが発生した場合"""
        df = pd.DataFrame([{"start": 0.0, "end": 1.0, "text": "test"}])
        
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            # パーミッションエラーが再発生することを確認
            with pytest.raises(PermissionError, match="Permission denied"):
                save_dataframe_to_local(df, str(temp_directory / "test.json"))


class TestParameterValidation:
    """パラメータバリデーションのテスト"""
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_parameter_combinations(self, sample_audio_file, temp_directory):
        """さまざまなパラメータ組み合わせのテスト"""
        mock_segments = [Mock(start=0.0, end=1.0, text="test")]
        mock_info = Mock()
        mock_info.language = "ja"
        
        mock_model = Mock()
        mock_model.transcribe.return_value = (mock_segments, mock_info)
        
        with patch("whisper_batch.app.transcribe._get_whisper_model", return_value=mock_model), \
             patch("whisper_batch.app.transcribe.save_dataframe"):
            
            # 様々なパラメータ組み合わせをテスト
            test_params = [
                {"language": "ja", "initial_prompt": "日本語音声"},
                {"language": "en", "initial_prompt": "English audio"},
                {"language": "auto", "initial_prompt": ""},
                {"language": "", "initial_prompt": "空言語設定"},
            ]
            
            for i, params in enumerate(test_params):
                output_file = temp_directory / f"param_test_{i}.json"
                
                # パラメータエラーが発生しないことを確認
                result = transcribe_audio(
                    sample_audio_file,
                    str(output_file),
                    device="cpu",
                    **params
                )
                
                assert isinstance(result, pd.DataFrame)
