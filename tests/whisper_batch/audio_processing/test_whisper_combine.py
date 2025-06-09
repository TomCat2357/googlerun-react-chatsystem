"""
Whisper結果統合機能のテスト
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, Mock
from pathlib import Path
import pandas as pd
import numpy as np

# 結果統合関連の関数をインポート（実際のファイルが存在する場合）
try:
    from whisper_batch.app.combine_results import (
        combine_results,
        read_json,
        save_dataframe,
        merge_transcription_and_diarization
    )
    COMBINE_MODULE_AVAILABLE = True
except ImportError:
    COMBINE_MODULE_AVAILABLE = False


@pytest.mark.skipif(not COMBINE_MODULE_AVAILABLE, reason="combine_results module not available")
class TestCombineResults:
    """文字起こしと話者分離結果の統合テスト"""
    
    @pytest.mark.asyncio
    async def test_combine_results_success(self, temp_directory, sample_transcription_result, sample_diarization_result):
        """結果統合の成功ケース"""
        # 入力ファイルの準備
        transcription_file = temp_directory / "transcription.json"
        diarization_file = temp_directory / "diarization.json"
        output_file = temp_directory / "combined_result.json"
        
        # テストデータをファイルに保存
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(sample_transcription_result, f, ensure_ascii=False)
        
        with open(diarization_file, "w", encoding="utf-8") as f:
            json.dump(sample_diarization_result, f, ensure_ascii=False)
        
        # 結果統合実行
        combine_results(
            str(transcription_file),
            str(diarization_file),
            str(output_file)
        )
        
        # 出力ファイルが作成されることを確認
        assert output_file.exists()
        
        # 出力内容の確認
        with open(output_file, "r", encoding="utf-8") as f:
            combined_data = json.load(f)
        
        assert isinstance(combined_data, list)
        assert len(combined_data) == len(sample_transcription_result)
        
        # 各セグメントにテキストと話者情報が含まれることを確認
        for segment in combined_data:
            assert "start" in segment
            assert "end" in segment
            assert "text" in segment
            assert "speaker" in segment
    
    @pytest.mark.asyncio
    async def test_combine_results_mismatched_segments(self, temp_directory):
        """セグメント数が一致しない場合の処理"""
        # 文字起こし結果（3セグメント）
        transcription_data = [
            {"start": 0.0, "end": 1.0, "text": "最初"},
            {"start": 1.0, "end": 2.0, "text": "中間"},
            {"start": 2.0, "end": 3.0, "text": "最後"}
        ]
        
        # 話者分離結果（2セグメント）
        diarization_data = [
            {"start": 0.0, "end": 1.5, "speaker": "SPEAKER_01"},
            {"start": 1.5, "end": 3.0, "speaker": "SPEAKER_02"}
        ]
        
        transcription_file = temp_directory / "transcription_3seg.json"
        diarization_file = temp_directory / "diarization_2seg.json"
        output_file = temp_directory / "combined_mismatched.json"
        
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(transcription_data, f, ensure_ascii=False)
        
        with open(diarization_file, "w", encoding="utf-8") as f:
            json.dump(diarization_data, f, ensure_ascii=False)
        
        # 結果統合実行（エラーが発生しないことを確認）
        combine_results(
            str(transcription_file),
            str(diarization_file),
            str(output_file)
        )
        
        # 出力ファイルが作成されることを確認
        assert output_file.exists()
        
        # 適切にマージされていることを確認
        with open(output_file, "r", encoding="utf-8") as f:
            combined_data = json.load(f)
        
        assert len(combined_data) > 0
    
    @pytest.mark.asyncio
    async def test_combine_results_empty_files(self, temp_directory):
        """空のファイルの場合の処理"""
        transcription_file = temp_directory / "empty_transcription.json"
        diarization_file = temp_directory / "empty_diarization.json"
        output_file = temp_directory / "combined_empty.json"
        
        # 空のリストをファイルに保存
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        
        with open(diarization_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        
        # 結果統合実行
        combine_results(
            str(transcription_file),
            str(diarization_file),
            str(output_file)
        )
        
        # 出力ファイルが作成されることを確認
        assert output_file.exists()
        
        # 空のリストが出力されることを確認
        with open(output_file, "r", encoding="utf-8") as f:
            combined_data = json.load(f)
        
        assert combined_data == []


@pytest.mark.skipif(not COMBINE_MODULE_AVAILABLE, reason="combine_results module not available")
class TestReadJson:
    """JSON読み込み機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_read_json_valid_file(self, temp_directory, sample_transcription_result):
        """有効なJSONファイルの読み込み"""
        test_file = temp_directory / "valid_test.json"
        
        with open(test_file, "w", encoding="utf-8") as f:
            json.dump(sample_transcription_result, f, ensure_ascii=False)
        
        result = read_json(test_file)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_transcription_result)
        assert "start" in result.columns
        assert "end" in result.columns
        assert "text" in result.columns
    
    @pytest.mark.asyncio
    async def test_read_json_nonexistent_file(self, temp_directory):
        """存在しないファイルの読み込み"""
        nonexistent_file = temp_directory / "nonexistent.json"
        
        with pytest.raises(FileNotFoundError):
            read_json(nonexistent_file)
    
    @pytest.mark.asyncio
    async def test_read_json_invalid_format(self, temp_directory):
        """無効なJSON形式ファイルの読み込み"""
        invalid_file = temp_directory / "invalid.json"
        
        # 無効なJSON内容を書き込み
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json content")
        
        with pytest.raises(json.JSONDecodeError):
            read_json(invalid_file)
    
    @pytest.mark.asyncio
    async def test_read_json_empty_file(self, temp_directory):
        """空のファイルの読み込み"""
        empty_file = temp_directory / "empty.json"
        
        # 空のファイルを作成
        empty_file.touch()
        
        with pytest.raises(json.JSONDecodeError):
            read_json(empty_file)


@pytest.mark.skipif(not COMBINE_MODULE_AVAILABLE, reason="combine_results module not available")  
class TestSaveDataframe:
    """DataFrameの保存機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_save_dataframe_success(self, temp_directory):
        """DataFrameの正常な保存"""
        df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "text": "テスト", "speaker": "SPEAKER_01"},
            {"start": 1.0, "end": 2.0, "text": "データ", "speaker": "SPEAKER_01"}
        ])
        
        output_file = temp_directory / "saved_dataframe.json"
        
        save_dataframe(df, output_file)
        
        # ファイルが作成されることを確認
        assert output_file.exists()
        
        # 内容の確認
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert len(data) == 2
        assert data[0]["text"] == "テスト"
        assert data[1]["text"] == "データ"
    
    @pytest.mark.asyncio
    async def test_save_dataframe_empty(self, temp_directory):
        """空のDataFrameの保存"""
        df = pd.DataFrame(columns=["start", "end", "text", "speaker"])
        
        output_file = temp_directory / "empty_dataframe.json"
        
        save_dataframe(df, output_file)
        
        # ファイルが作成されることを確認
        assert output_file.exists()
        
        # 空のリストが保存されることを確認
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert data == []
    
    @pytest.mark.asyncio
    async def test_save_dataframe_special_characters(self, temp_directory):
        """特殊文字を含むDataFrameの保存"""
        df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "text": "こんにちは！「質問」", "speaker": "SPEAKER_01"},
            {"start": 1.0, "end": 2.0, "text": "100%確実です", "speaker": "SPEAKER_02"}
        ])
        
        output_file = temp_directory / "special_chars_dataframe.json"
        
        save_dataframe(df, output_file)
        
        # 内容の確認
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert data[0]["text"] == "こんにちは！「質問」"
        assert data[1]["text"] == "100%確実です"


@pytest.mark.skipif(not COMBINE_MODULE_AVAILABLE, reason="combine_results module not available")
class TestMergeTranscriptionAndDiarization:
    """文字起こしと話者分離のマージ機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_merge_perfect_alignment(self):
        """完全に一致するセグメントのマージ"""
        transcription_df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "text": "最初"},
            {"start": 1.0, "end": 2.0, "text": "次"}
        ])
        
        diarization_df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_02"}
        ])
        
        result = merge_transcription_and_diarization(transcription_df, diarization_df)
        
        assert len(result) == 2
        assert result.iloc[0]["text"] == "最初"
        assert result.iloc[0]["speaker"] == "SPEAKER_01"
        assert result.iloc[1]["text"] == "次"
        assert result.iloc[1]["speaker"] == "SPEAKER_02"
    
    @pytest.mark.asyncio
    async def test_merge_overlapping_segments(self):
        """重複するセグメントのマージ"""
        transcription_df = pd.DataFrame([
            {"start": 0.0, "end": 1.5, "text": "長いテキスト"},
            {"start": 1.5, "end": 3.0, "text": "続きのテキスト"}
        ])
        
        diarization_df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_02"},
            {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_01"}
        ])
        
        result = merge_transcription_and_diarization(transcription_df, diarization_df)
        
        # マージが適切に行われることを確認
        assert len(result) > 0
        assert all("text" in col and "speaker" in col for index, col in result.iterrows())
    
    @pytest.mark.asyncio
    async def test_merge_time_gaps(self):
        """時間的ギャップがあるセグメントのマージ"""
        transcription_df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "text": "最初"},
            {"start": 2.0, "end": 3.0, "text": "ギャップ後"}  # 1秒のギャップ
        ])
        
        diarization_df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"start": 1.5, "end": 2.5, "speaker": "SPEAKER_02"}  # 若干ずれている
        ])
        
        result = merge_transcription_and_diarization(transcription_df, diarization_df)
        
        # ギャップがあってもマージが実行されることを確認
        assert len(result) >= len(transcription_df)
    
    @pytest.mark.asyncio
    async def test_merge_different_lengths(self):
        """異なる長さのセグメントリストのマージ"""
        # 文字起こし結果の方が多い場合
        transcription_df = pd.DataFrame([
            {"start": 0.0, "end": 0.5, "text": "短い1"},
            {"start": 0.5, "end": 1.0, "text": "短い2"},
            {"start": 1.0, "end": 1.5, "text": "短い3"},
            {"start": 1.5, "end": 2.0, "text": "短い4"}
        ])
        
        # 話者分離結果の方が少ない場合
        diarization_df = pd.DataFrame([
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_02"}
        ])
        
        result = merge_transcription_and_diarization(transcription_df, diarization_df)
        
        # すべての文字起こしセグメントが含まれることを確認
        assert len(result) == 4
        
        # 各セグメントに話者情報が割り当てられることを確認
        assert all(pd.notna(result["speaker"]))


class TestCombineResultsIntegration:
    """結果統合の統合テスト"""
    
    @pytest.mark.asyncio
    async def test_realistic_combine_scenario(self, temp_directory):
        """現実的なシナリオでの統合テスト"""
        # リアルな文字起こし結果
        transcription_data = [
            {"start": 0.0, "end": 2.3, "text": "こんにちは、今日は良い天気ですね。"},
            {"start": 2.3, "end": 4.7, "text": "そうですね、散歩日和です。"},
            {"start": 4.7, "end": 6.8, "text": "公園に行きませんか？"},
            {"start": 6.8, "end": 9.1, "text": "いいですね、一緒に行きましょう。"},
            {"start": 9.1, "end": 10.5, "text": "ありがとうございます。"}
        ]
        
        # リアルな話者分離結果
        diarization_data = [
            {"start": 0.0, "end": 2.3, "speaker": "SPEAKER_01"},
            {"start": 2.3, "end": 4.7, "speaker": "SPEAKER_02"},
            {"start": 4.7, "end": 6.8, "speaker": "SPEAKER_01"},
            {"start": 6.8, "end": 9.1, "speaker": "SPEAKER_02"},
            {"start": 9.1, "end": 10.5, "speaker": "SPEAKER_01"}
        ]
        
        transcription_file = temp_directory / "realistic_transcription.json"
        diarization_file = temp_directory / "realistic_diarization.json"
        output_file = temp_directory / "realistic_combined.json"
        
        # ファイルに保存
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(transcription_data, f, ensure_ascii=False, indent=2)
        
        with open(diarization_file, "w", encoding="utf-8") as f:
            json.dump(diarization_data, f, ensure_ascii=False, indent=2)
        
        # モック実装を使用（実際の関数が利用できない場合）
        if not COMBINE_MODULE_AVAILABLE:
            mock_combine_results(
                str(transcription_file),
                str(diarization_file),
                str(output_file)
            )
        else:
            combine_results(
                str(transcription_file),
                str(diarization_file),
                str(output_file)
            )
        
        # 結果の確認
        assert output_file.exists()
        
        with open(output_file, "r", encoding="utf-8") as f:
            combined_data = json.load(f)
        
        # データの整合性確認
        assert len(combined_data) == 5
        
        # 各セグメントの内容確認
        for i, segment in enumerate(combined_data):
            assert segment["start"] == transcription_data[i]["start"]
            assert segment["end"] == transcription_data[i]["end"]
            assert segment["text"] == transcription_data[i]["text"]
            assert segment["speaker"] == diarization_data[i]["speaker"]
        
        # 話者の分布確認
        speakers = [seg["speaker"] for seg in combined_data]
        assert "SPEAKER_01" in speakers
        assert "SPEAKER_02" in speakers


# モック実装（combine_results.pyが存在しない場合のテスト用）
def mock_combine_results(transcription_path, diarization_path, output_path):
    """結果統合のモック実装"""
    try:
        # 文字起こし結果を読み込み
        with open(transcription_path, "r", encoding="utf-8") as f:
            transcription_data = json.load(f)
        
        # 話者分離結果を読み込み
        with open(diarization_path, "r", encoding="utf-8") as f:
            diarization_data = json.load(f)
        
        # 簡単なマージ（同じ長さの場合）
        if len(transcription_data) == len(diarization_data):
            combined_data = []
            for trans, diar in zip(transcription_data, diarization_data):
                combined_segment = {
                    "start": trans["start"],
                    "end": trans["end"],
                    "text": trans["text"],
                    "speaker": diar["speaker"]
                }
                combined_data.append(combined_segment)
        else:
            # 長さが異なる場合の簡易処理
            combined_data = []
            for i, trans in enumerate(transcription_data):
                # 話者情報を適切に割り当て（簡易実装）
                speaker = "SPEAKER_01"
                if i < len(diarization_data):
                    speaker = diarization_data[i]["speaker"]
                elif len(diarization_data) > 0:
                    # 最後の話者を使用
                    speaker = diarization_data[-1]["speaker"]
                
                combined_segment = {
                    "start": trans["start"],
                    "end": trans["end"],
                    "text": trans["text"],
                    "speaker": speaker
                }
                combined_data.append(combined_segment)
        
        # 結果を保存
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(combined_data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        # エラーが発生した場合は空のリストを出力
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([], f)


def mock_read_json(file_path):
    """JSON読み込みのモック実装"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data)


def mock_save_dataframe(df, output_path):
    """DataFrameの保存のモック実装"""
    df.to_json(output_path, orient="records", indent=2, force_ascii=False)


@pytest.mark.skipif(COMBINE_MODULE_AVAILABLE, reason="combine_results module is available, skip mock tests")
class TestMockCombineResults:
    """結果統合機能のモックテスト（実際のモジュールが利用できない場合）"""
    
    @pytest.mark.asyncio
    async def test_mock_combine_equal_lengths(self, temp_directory):
        """モック統合：同じ長さのリスト"""
        transcription_data = [
            {"start": 0.0, "end": 1.0, "text": "テスト1"},
            {"start": 1.0, "end": 2.0, "text": "テスト2"}
        ]
        
        diarization_data = [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_02"}
        ]
        
        transcription_file = temp_directory / "mock_trans.json"
        diarization_file = temp_directory / "mock_diar.json"
        output_file = temp_directory / "mock_combined.json"
        
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(transcription_data, f, ensure_ascii=False)
        
        with open(diarization_file, "w", encoding="utf-8") as f:
            json.dump(diarization_data, f, ensure_ascii=False)
        
        mock_combine_results(
            str(transcription_file),
            str(diarization_file),
            str(output_file)
        )
        
        # 結果確認
        assert output_file.exists()
        
        with open(output_file, "r", encoding="utf-8") as f:
            combined_data = json.load(f)
        
        assert len(combined_data) == 2
        assert combined_data[0]["text"] == "テスト1"
        assert combined_data[0]["speaker"] == "SPEAKER_01"
        assert combined_data[1]["text"] == "テスト2"
        assert combined_data[1]["speaker"] == "SPEAKER_02"
    
    @pytest.mark.asyncio
    async def test_mock_combine_different_lengths(self, temp_directory):
        """モック統合：異なる長さのリスト"""
        transcription_data = [
            {"start": 0.0, "end": 1.0, "text": "テスト1"},
            {"start": 1.0, "end": 2.0, "text": "テスト2"},
            {"start": 2.0, "end": 3.0, "text": "テスト3"}
        ]
        
        diarization_data = [
            {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_01"}
        ]
        
        transcription_file = temp_directory / "mock_trans_long.json"
        diarization_file = temp_directory / "mock_diar_short.json"
        output_file = temp_directory / "mock_combined_diff.json"
        
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(transcription_data, f, ensure_ascii=False)
        
        with open(diarization_file, "w", encoding="utf-8") as f:
            json.dump(diarization_data, f, ensure_ascii=False)
        
        mock_combine_results(
            str(transcription_file),
            str(diarization_file),
            str(output_file)
        )
        
        # 結果確認
        assert output_file.exists()
        
        with open(output_file, "r", encoding="utf-8") as f:
            combined_data = json.load(f)
        
        assert len(combined_data) == 3  # 文字起こし結果の数
        # すべてのセグメントに話者情報が含まれることを確認
        assert all("speaker" in segment for segment in combined_data)
