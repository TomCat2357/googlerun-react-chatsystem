"""
Whisper API Refactored Testing Suite

既存のtest_whisper_api.pyを改善し、振る舞い駆動設計とアドバンステスト技術を適用:
- テストダブル戦略の最適化（モック最小化、実オブジェクト優先）
- 包括的パラメータ化テストによるエッジケース検証
- create_autospec + side_effect パターンの徹底適用
- 振る舞い検証 vs 実装詳細テストの分離
"""

import pytest
import json
import uuid
import time
from unittest.mock import patch, Mock, MagicMock, create_autospec
from fastapi import HTTPException
from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
from faker import Faker

from common_utils.class_types import WhisperUploadRequest, WhisperEditRequest, WhisperSegment, WhisperSpeakerConfigRequest, SpeakerConfigItem
from backend.app.api.whisper import router


# ==============================================================================
# Test Data Factories for API Testing
# ==============================================================================

class WhisperAPIDataFactory:
    """Whisper API テストデータファクトリー（Fakerベース）"""
    
    def __init__(self):
        self.fake = Faker(['ja_JP', 'en_US'])
        self.fake.seed_instance(98765)  # 再現可能な結果
    
    def create_upload_request_data(self, valid: bool = True, **kwargs) -> Dict[str, Any]:
        """アップロードリクエストデータを生成"""
        if valid:
            defaults = {
                "audio_data": self.fake.sha256()[:100],  # Base64風データ
                "filename": f"{self.fake.slug()}.wav",
                "gcs_object": f"whisper/{self.fake.uuid4()}.wav",
                "original_name": f"{self.fake.word()}_recording.wav",
                "description": self.fake.text(max_nb_chars=100),
                "recording_date": self.fake.date().isoformat(),
                "language": self.fake.random_element(["ja", "en", "auto"]),
                "initial_prompt": self.fake.text(max_nb_chars=50),
                "tags": [self.fake.word() for _ in range(3)],
                "num_speakers": self.fake.random_int(min=1, max=5),
                "min_speakers": 1,
                "max_speakers": 10
            }
        else:
            # 無効なデータ（必須フィールド欠落）
            defaults = {
                "filename": "incomplete.wav"
                # audio_data欠落
            }
        
        defaults.update(kwargs)
        return defaults
    
    @pytest.mark.parametrize(
        ["format", "is_valid", "size_mb", "expected_behavior"],
        [
            ("wav", True, 5, "accept"),
            ("mp3", True, 10, "accept"),
            ("m4a", True, 50, "accept"),
            ("flac", True, 80, "warn_large"),
            ("pdf", False, 1, "reject_format"),
            ("wav", False, 150, "reject_size"),
            ("mp3", True, 0.01, "accept_small"),
        ],
        ids=[
            "WAV_5MB_正常受付",
            "MP3_10MB_正常受付",
            "M4A_50MB_正常受付",
            "FLAC_80MB_大容量警告",
            "PDF_1MB_フォーマット拒否",
            "WAV_150MB_サイズ拒否",
            "MP3_極小_正常受付",
        ],
    )
    def create_format_test_scenarios(self, format: str, is_valid: bool, size_mb: float, expected_behavior: str):
        """フォーマット別テストシナリオを生成"""
        return {
            "filename": f"{self.fake.slug()}.{format}",
            "format": format,
            "is_valid": is_valid,
            "size_bytes": int(size_mb * 1024 * 1024),
            "expected_behavior": expected_behavior,
            "content_type": f"audio/{format}" if is_valid else f"application/{format}"
        }
    
    def create_realistic_transcription_segments(self, segment_count: int = 10, language: str = "ja") -> List[Dict[str, Any]]:
        """現実的な文字起こしセグメントを生成"""
        if language == "ja":
            # 実際の会議で使われそうな表現
            sample_phrases = [
                "おはようございます、それでは会議を始めさせていただきます",
                "まず、前回の議事録の確認からお願いします",
                "進捗状況はいかがでしょうか",
                "スケジュール通りに進んでおります",
                "こちらの件について質問があります",
                "少し遅れが生じていますが、来週には追いつく予定です",
                "承知いたしました、検討させていただきます",
                "他にご質問はございますか",
                "それでは次の議題に移らせていただきます",
                "今日はお疲れ様でした、次回もよろしくお願いします"
            ]
        else:
            sample_phrases = [
                "Good morning everyone, let's start the meeting",
                "First, let's review the minutes from last meeting",
                "How is the progress on the project",
                "We are on track with the schedule",
                "I have a question about this matter",
                "We are slightly behind but will catch up next week",
                "Understood, we will consider this",
                "Any other questions",
                "Let's move on to the next topic",
                "Thank you for your time today"
            ]
        
        segments = []
        current_time = 0.0
        speakers = ["SPEAKER_01", "SPEAKER_02", "SPEAKER_03"]
        
        for i in range(min(segment_count, len(sample_phrases))):
            duration = self.fake.random.uniform(2.0, 8.0)
            speaker = self.fake.random.choice(speakers)
            
            segments.append({
                "start": round(current_time, 1),
                "end": round(current_time + duration, 1),
                "text": sample_phrases[i],
                "speaker": speaker,
                "confidence": round(self.fake.random.uniform(0.85, 0.99), 3)
            })
            
            current_time += duration + self.fake.random.uniform(0.2, 1.0)
        
        return segments
    
    def create_speaker_config_variations(self) -> List[Dict[str, Any]]:
        """多様なスピーカー設定パターンを生成"""
        color_palette = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8"]
        
        variations = [
            # 最小構成（1話者）
            {
                "SPEAKER_01": {
                    "name": "発表者",
                    "color": color_palette[0]
                }
            },
            # 標準構成（2話者）
            {
                "SPEAKER_01": {
                    "name": "司会者",
                    "color": color_palette[0]
                },
                "SPEAKER_02": {
                    "name": "参加者A",
                    "color": color_palette[1]
                }
            },
            # 複雑構成（多話者）
            {
                f"SPEAKER_{i:02d}": {
                    "name": f"参加者{chr(ord('A') + i - 1)}",
                    "color": color_palette[(i - 1) % len(color_palette)]
                }
                for i in range(1, 6)
            },
            # 英語構成
            {
                "SPEAKER_01": {
                    "name": "Moderator",
                    "color": color_palette[0]
                },
                "SPEAKER_02": {
                    "name": "Participant A",
                    "color": color_palette[1]
                },
                "SPEAKER_03": {
                    "name": "Participant B",
                    "color": color_palette[2]
                }
            }
        ]
        
        return variations


class WhisperAPIErrorFactory:
    """Whisper API エラーシナリオファクトリー"""
    
    def __init__(self):
        self.fake = Faker(['ja_JP'])
        self.fake.seed_instance(54321)
    
    def create_error_scenarios(self) -> List[Dict[str, Any]]:
        """包括的なエラーシナリオを生成"""
        return [
            {
                "scenario_name": "認証失敗",
                "error_type": "AuthenticationError",
                "http_status": 401,
                "error_data": {"headers": {}},  # Authorization ヘッダーなし
                "expected_message": "authentication.*required",
                "retry_possible": False
            },
            {
                "scenario_name": "無効なファイルフォーマット",
                "error_type": "ValidationError",
                "http_status": 400,
                "error_data": {
                    "filename": "document.pdf",
                    "content_type": "application/pdf"
                },
                "expected_message": "無効な音声フォーマット",
                "retry_possible": False
            },
            {
                "scenario_name": "ファイルサイズ超過",
                "error_type": "PayloadTooLarge",
                "http_status": 413,
                "error_data": {
                    "size": 200 * 1024 * 1024,  # 200MB
                    "content_type": "audio/wav"
                },
                "expected_message": "ファイルサイズが大きすぎます",
                "retry_possible": False
            },
            {
                "scenario_name": "必須フィールド欠落",
                "error_type": "ValidationError",
                "http_status": 422,
                "error_data": {"filename": "test.wav"},  # audio_data欠落
                "expected_message": "validation.*error",
                "retry_possible": False
            },
            {
                "scenario_name": "ストレージサービスエラー",
                "error_type": "ServiceUnavailable",
                "http_status": 503,
                "error_data": {"service": "storage"},
                "expected_message": "storage.*unavailable",
                "retry_possible": True
            },
            {
                "scenario_name": "処理タイムアウト",
                "error_type": "TimeoutError",
                "http_status": 504,
                "error_data": {"timeout_seconds": 30},
                "expected_message": "processing.*timeout",
                "retry_possible": True
            },
            {
                "scenario_name": "同時接続数制限",
                "error_type": "TooManyRequests",
                "http_status": 429,
                "error_data": {"limit": 10, "current": 11},
                "expected_message": "too.*many.*requests",
                "retry_possible": True
            }
        ]


# ==============================================================================
# Behavioral Separation: API Contract vs Implementation Details
# ==============================================================================

class WhisperAPIContractCore:
    """Whisper API契約の中核ロジック（純粋関数）"""
    
    VALID_AUDIO_FORMATS = {"wav", "mp3", "m4a", "flac", "ogg", "webm"}
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    MIN_FILE_SIZE = 1024  # 1KB
    SUPPORTED_LANGUAGES = {"ja", "en", "auto", "zh", "ko", "es", "fr", "de"}
    
    @staticmethod
    def validate_upload_request_format(filename: str, content_type: str = None) -> Dict[str, Any]:
        """アップロードリクエストフォーマットの検証"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        if not filename or not isinstance(filename, str):
            result["errors"].append("ファイル名が無効です")
            result["valid"] = False
            return result
        
        # 拡張子検証
        extension = Path(filename).suffix.lower().lstrip('.')
        if extension not in WhisperAPIContractCore.VALID_AUDIO_FORMATS:
            result["errors"].append(f"サポートされていない音声フォーマット: {extension}")
            result["valid"] = False
        
        # Content-Type検証（提供された場合）
        if content_type and not content_type.startswith("audio/"):
            result["warnings"].append(f"Content-Typeが音声形式ではありません: {content_type}")
        
        return result
    
    @staticmethod
    def validate_file_size(size_bytes: int) -> Dict[str, Any]:
        """ファイルサイズの検証"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        if not isinstance(size_bytes, int) or size_bytes <= 0:
            result["errors"].append("無効なファイルサイズ")
            result["valid"] = False
            return result
        
        if size_bytes < WhisperAPIContractCore.MIN_FILE_SIZE:
            result["warnings"].append(f"ファイルサイズが小さすぎます: {size_bytes} bytes")
        elif size_bytes > WhisperAPIContractCore.MAX_FILE_SIZE:
            result["errors"].append(f"ファイルサイズが大きすぎます: {size_bytes} bytes")
            result["valid"] = False
        elif size_bytes > WhisperAPIContractCore.MAX_FILE_SIZE * 0.8:
            result["warnings"].append("大きなファイルです。処理に時間がかかる可能性があります")
        
        return result
    
    @staticmethod
    def validate_language_setting(language: str) -> bool:
        """言語設定の検証"""
        if not language or not isinstance(language, str):
            return False
        return language.lower() in WhisperAPIContractCore.SUPPORTED_LANGUAGES
    
    @staticmethod
    def calculate_estimated_processing_time(file_size: int, num_speakers: int = 1, language: str = "auto") -> int:
        """推定処理時間の計算（秒）"""
        # ベース処理時間（ファイルサイズベース）
        base_time_per_mb = 30  # 1MBあたり30秒
        size_mb = file_size / (1024 * 1024)
        base_time = max(10, size_mb * base_time_per_mb)
        
        # 話者数による調整
        speaker_multiplier = 1.0 + (num_speakers - 1) * 0.3  # 話者1人増加で30%増
        
        # 言語による調整
        if language == "auto":
            language_multiplier = 1.2  # 自動検出は20%増
        elif language in ["ja", "zh", "ko"]:
            language_multiplier = 1.1  # アジア言語は10%増
        else:
            language_multiplier = 1.0
        
        total_time = base_time * speaker_multiplier * language_multiplier
        return int(total_time)
    
    @staticmethod
    def determine_response_format(request_data: Dict[str, Any]) -> Dict[str, Any]:
        """レスポンス形式の決定"""
        response_format = {
            "include_timestamps": True,
            "include_speaker_labels": False,
            "include_confidence_scores": False,
            "format_version": "v1"
        }
        
        # 話者分離が有効な場合
        if request_data.get("num_speakers", 1) > 1 or request_data.get("max_speakers", 1) > 1:
            response_format["include_speaker_labels"] = True
        
        # 詳細モードが要求された場合
        if request_data.get("detailed_output", False):
            response_format["include_confidence_scores"] = True
            response_format["format_version"] = "v2"
        
        return response_format


class WhisperAPIServiceWorkflow:
    """Whisper APIサービスワークフロー（外部サービス連携）"""
    
    def __init__(self, contract_validator: WhisperAPIContractCore, storage_service, auth_service, processing_service):
        self.validator = contract_validator
        self.storage_service = storage_service
        self.auth_service = auth_service
        self.processing_service = processing_service
    
    async def process_upload_request(self, request_data: Dict[str, Any], user_context: Dict[str, Any]) -> Dict[str, Any]:
        """アップロードリクエスト処理ワークフロー"""
        try:
            # 1. 中核ロジック：契約検証
            format_validation = self.validator.validate_upload_request_format(
                request_data.get("filename", ""),
                request_data.get("content_type")
            )
            
            if not format_validation["valid"]:
                raise ValueError(f"フォーマット検証失敗: {format_validation['errors']}")
            
            # 2. 外部サービス：認証・権限確認
            await self.auth_service.verify_upload_permission(user_context)
            
            # 3. 外部サービス：ストレージ操作
            file_info = await self.storage_service.get_upload_file_info(request_data)
            
            # 4. 中核ロジック：ファイルサイズ検証
            size_validation = self.validator.validate_file_size(file_info["size"])
            if not size_validation["valid"]:
                raise ValueError(f"ファイルサイズ検証失敗: {size_validation['errors']}")
            
            # 5. 中核ロジック：処理時間推定
            estimated_time = self.validator.calculate_estimated_processing_time(
                file_info["size"],
                request_data.get("num_speakers", 1),
                request_data.get("language", "auto")
            )
            
            # 6. 外部サービス：ジョブキューイング
            job_id = await self.processing_service.enqueue_transcription_job(
                request_data, file_info, user_context
            )
            
            # 7. 中核ロジック：レスポンス形式決定
            response_format = self.validator.determine_response_format(request_data)
            
            return {
                "status": "success",
                "job_id": job_id,
                "estimated_processing_time_seconds": estimated_time,
                "response_format": response_format,
                "warnings": format_validation["warnings"] + size_validation["warnings"]
            }
            
        except Exception as e:
            # エラーハンドリングフロー
            await self.processing_service.log_upload_error(str(e), request_data, user_context)
            raise
    
    async def retrieve_job_status(self, job_identifier: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
        """ジョブステータス取得ワークフロー"""
        # 1. 外部サービス：認証・権限確認
        await self.auth_service.verify_job_access_permission(job_identifier, user_context)
        
        # 2. 外部サービス：ジョブ情報取得
        job_info = await self.processing_service.get_job_status(job_identifier)
        
        # 3. 中核ロジック：レスポンス形式決定（ジョブの設定に基づく）
        response_format = self.validator.determine_response_format(job_info.get("original_request", {}))
        
        return {
            "job_id": job_identifier,
            "status": job_info["status"],
            "progress": job_info.get("progress", 0),
            "result_available": job_info["status"] == "completed",
            "response_format": response_format
        }


# ==============================================================================
# Core Contract Tests (Comprehensive)
# ==============================================================================

class TestWhisperAPIContractCore:
    """Whisper API契約中核ロジックの網羅的テスト"""
    
    @pytest.mark.parametrize(
        ["filename", "content_type", "expected_valid", "expected_error_count"],
        [
            # 有効なフォーマット
            ("recording.wav", "audio/wav", True, 0),
            ("speech.mp3", "audio/mp3", True, 0),
            ("audio.m4a", "audio/m4a", True, 0),
            ("music.flac", "audio/flac", True, 0),
            ("voice.ogg", "audio/ogg", True, 0),
            ("stream.webm", "audio/webm", True, 0),
            
            # 大文字小文字のバリエーション
            ("RECORDING.WAV", "audio/wav", True, 0),
            ("Speech.MP3", "audio/mp3", True, 0),
            
            # 無効なフォーマット
            ("document.pdf", "application/pdf", False, 1),
            ("image.jpg", "image/jpeg", False, 1),
            ("video.mp4", "video/mp4", False, 1),
            ("text.txt", "text/plain", False, 1),
            
            # エッジケース
            ("", None, False, 1),
            (None, None, False, 1),
            ("no_extension", None, False, 1),
            (".wav", "audio/wav", True, 0),  # 拡張子のみ
            ("multiple.dots.in.filename.wav", "audio/wav", True, 0),
        ],
        ids=[
            "WAV_標準",
            "MP3_標準",
            "M4A_標準",
            "FLAC_標準",
            "OGG_標準",
            "WEBM_標準",
            "WAV_大文字",
            "MP3_混合",
            "PDF_無効",
            "JPG_無効",
            "MP4_無効",
            "TXT_無効",
            "空文字列_無効",
            "None値_無効",
            "拡張子なし_無効",
            "拡張子のみ_有効",
            "複数ドット_有効",
        ],
    )
    def test_validate_upload_request_format_全フォーマットパターンで正しい結果(
        self, filename, content_type, expected_valid, expected_error_count
    ):
        """アップロードリクエストフォーマット検証が全パターンで正しい結果を返すこと"""
        # Act（実行）
        result = WhisperAPIContractCore.validate_upload_request_format(filename, content_type)
        
        # Assert（検証）
        assert result["valid"] == expected_valid
        assert len(result["errors"]) == expected_error_count
        assert isinstance(result["warnings"], list)
    
    @pytest.mark.parametrize(
        ["size_bytes", "expected_valid", "expected_warnings"],
        [
            # 有効範囲
            (1024, True, 0),                           # 最小サイズ
            (1024 * 1024, True, 0),                    # 1MB
            (50 * 1024 * 1024, True, 0),               # 50MB
            (80 * 1024 * 1024, True, 1),               # 80MB（警告）
            (100 * 1024 * 1024, True, 1),              # 100MB（上限、警告）
            
            # 無効範囲
            (0, False, 0),                              # ゼロ
            (-1000, False, 0),                          # 負数
            (100 * 1024 * 1024 + 1, False, 0),        # 上限超過
            (200 * 1024 * 1024, False, 0),            # 大幅超過
            
            # 警告範囲
            (500, True, 1),                            # 極小ファイル
        ],
        ids=[
            "最小サイズ1KB_有効",
            "1MB_有効",
            "50MB_有効",
            "80MB_警告付き",
            "100MB上限_警告付き",
            "ゼロサイズ_無効",
            "負数サイズ_無効",
            "上限1バイト超過_無効",
            "大幅超過_無効",
            "極小ファイル_警告付き",
        ],
    )
    def test_validate_file_size_境界値と警告で正しい結果(
        self, size_bytes, expected_valid, expected_warnings
    ):
        """ファイルサイズ検証が境界値と警告条件で正しい結果を返すこと"""
        # Act（実行）
        result = WhisperAPIContractCore.validate_file_size(size_bytes)
        
        # Assert（検証）
        assert result["valid"] == expected_valid
        assert len(result["warnings"]) == expected_warnings
    
    @pytest.mark.parametrize(
        ["language", "expected_valid"],
        [
            ("ja", True),
            ("en", True),
            ("auto", True),
            ("zh", True),
            ("ko", True),
            ("es", True),
            ("fr", True),
            ("de", True),
            # 無効なケース
            ("", False),
            (None, False),
            ("invalid", False),
            ("jp", False),  # 正しくはja
            ("chinese", False),  # 正しくはzh
        ],
        ids=[
            "日本語_有効",
            "英語_有効",
            "自動検出_有効",
            "中国語_有効",
            "韓国語_有効",
            "スペイン語_有効",
            "フランス語_有効",
            "ドイツ語_有効",
            "空文字列_無効",
            "None値_無効",
            "無効言語_無効",
            "間違いやすいjp_無効",
            "英語名chinese_無効",
        ],
    )
    def test_validate_language_setting_サポート言語で正しい結果(self, language, expected_valid):
        """言語設定検証がサポート言語で正しい結果を返すこと"""
        # Act（実行）
        result = WhisperAPIContractCore.validate_language_setting(language)
        
        # Assert（検証）
        assert result == expected_valid
    
    @pytest.mark.parametrize(
        ["file_size_mb", "num_speakers", "language", "expected_range"],
        [
            # 基本パターン
            (1, 1, "en", (30, 50)),        # 1MB、単一話者、英語
            (10, 1, "ja", (300, 400)),     # 10MB、単一話者、日本語
            (50, 3, "auto", (2000, 3000)), # 50MB、3話者、自動検出
            
            # エッジケース
            (0.1, 1, "en", (10, 30)),      # 極小ファイル
            (100, 8, "zh", (4000, 6000)),  # 大ファイル、多話者
        ],
        ids=[
            "1MB単一話者英語_基本処理時間",
            "10MB単一話者日本語_中程度処理時間",
            "50MB複数話者自動_長時間処理",
            "極小ファイル_最小処理時間",
            "大ファイル多話者_最大処理時間",
        ],
    )
    def test_calculate_estimated_processing_time_各条件で妥当な推定時間(
        self, file_size_mb, num_speakers, language, expected_range
    ):
        """推定処理時間計算が各条件で妥当な時間を返すこと"""
        # Arrange（準備）
        file_size_bytes = int(file_size_mb * 1024 * 1024)
        
        # Act（実行）
        estimated_time = WhisperAPIContractCore.calculate_estimated_processing_time(
            file_size_bytes, num_speakers, language
        )
        
        # Assert（検証）
        min_expected, max_expected = expected_range
        assert min_expected <= estimated_time <= max_expected
        assert estimated_time >= 10  # 最小10秒
    
    @pytest.mark.parametrize(
        ["request_data", "expected_speaker_labels", "expected_confidence"],
        [
            # 基本パターン
            ({}, False, False),
            ({"num_speakers": 1}, False, False),
            ({"num_speakers": 2}, True, False),
            ({"max_speakers": 3}, True, False),
            ({"detailed_output": True}, False, True),
            ({"num_speakers": 3, "detailed_output": True}, True, True),
        ],
        ids=[
            "デフォルト設定",
            "単一話者明示",
            "複数話者設定",
            "最大話者設定",
            "詳細出力要求",
            "複数話者詳細出力",
        ],
    )
    def test_determine_response_format_各設定で適切なフォーマット決定(
        self, request_data, expected_speaker_labels, expected_confidence
    ):
        """レスポンス形式決定が各設定で適切なフォーマットを返すこと"""
        # Act（実行）
        response_format = WhisperAPIContractCore.determine_response_format(request_data)
        
        # Assert（検証）
        assert response_format["include_speaker_labels"] == expected_speaker_labels
        assert response_format["include_confidence_scores"] == expected_confidence
        assert response_format["include_timestamps"] == True  # 常にtrue
        assert "format_version" in response_format


# ==============================================================================
# Service Workflow Tests (Representative Cases)
# ==============================================================================

class TestWhisperAPIServiceWorkflow:
    """Whisper APIサービスワークフローテスト（代表例のみ）"""
    
    @pytest.fixture
    def workflow_setup(self):
        """ワークフローテスト用セットアップ"""
        contract_validator = WhisperAPIContractCore()
        
        # 外部サービスのモック（autospec使用）
        mock_storage = create_autospec(object, spec_set=True)
        mock_storage.get_upload_file_info = Mock()
        
        mock_auth = create_autospec(object, spec_set=True)
        mock_auth.verify_upload_permission = Mock()
        mock_auth.verify_job_access_permission = Mock()
        
        mock_processing = create_autospec(object, spec_set=True)
        mock_processing.enqueue_transcription_job = Mock()
        mock_processing.get_job_status = Mock()
        mock_processing.log_upload_error = Mock()
        
        workflow = WhisperAPIServiceWorkflow(
            contract_validator, mock_storage, mock_auth, mock_processing
        )
        
        return {
            "workflow": workflow,
            "storage_mock": mock_storage,
            "auth_mock": mock_auth,
            "processing_mock": mock_processing
        }
    
    @pytest.mark.asyncio
    async def test_process_upload_request_正常なエンドツーエンドワークフロー(self, workflow_setup):
        """アップロードリクエスト処理の正常なエンドツーエンドワークフローが期待通りに動作すること"""
        # Arrange（準備）
        workflow = workflow_setup["workflow"]
        storage_mock = workflow_setup["storage_mock"]
        auth_mock = workflow_setup["auth_mock"]
        processing_mock = workflow_setup["processing_mock"]
        
        request_data = {
            "filename": "meeting-recording.wav",
            "content_type": "audio/wav",
            "num_speakers": 3,
            "language": "ja",
            "detailed_output": True
        }
        
        user_context = {
            "user_id": "user-123",
            "permissions": ["upload_audio"]
        }
        
        # 外部サービスの正常な応答を設定
        auth_mock.verify_upload_permission.return_value = None
        storage_mock.get_upload_file_info.return_value = {
            "size": 25 * 1024 * 1024,  # 25MB
            "content_type": "audio/wav"
        }
        processing_mock.enqueue_transcription_job.return_value = "job-12345"
        
        # Act（実行）
        result = await workflow.process_upload_request(request_data, user_context)
        
        # Assert（検証）
        assert result["status"] == "success"
        assert result["job_id"] == "job-12345"
        assert "estimated_processing_time_seconds" in result
        assert result["response_format"]["include_speaker_labels"] == True
        assert result["response_format"]["include_confidence_scores"] == True
        
        # 外部サービス呼び出し確認
        auth_mock.verify_upload_permission.assert_called_once_with(user_context)
        storage_mock.get_upload_file_info.assert_called_once_with(request_data)
        processing_mock.enqueue_transcription_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_upload_request_フォーマット検証失敗でエラー(self, workflow_setup):
        """無効フォーマットの場合に適切なエラーハンドリングが動作すること"""
        # Arrange（準備）
        workflow = workflow_setup["workflow"]
        processing_mock = workflow_setup["processing_mock"]
        
        request_data = {
            "filename": "document.pdf",  # 無効フォーマット
            "content_type": "application/pdf"
        }
        
        user_context = {"user_id": "user-123"}
        
        processing_mock.log_upload_error.return_value = None
        
        # Act & Assert（実行・検証）
        with pytest.raises(ValueError, match="フォーマット検証失敗"):
            await workflow.process_upload_request(request_data, user_context)
        
        # エラーログが記録されたことを確認
        processing_mock.log_upload_error.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_job_status_正常な取得ワークフロー(self, workflow_setup):
        """ジョブステータス取得の正常なワークフローが期待通りに動作すること"""
        # Arrange（準備）
        workflow = workflow_setup["workflow"]
        auth_mock = workflow_setup["auth_mock"]
        processing_mock = workflow_setup["processing_mock"]
        
        job_identifier = "job-67890"
        user_context = {"user_id": "user-456"}
        
        # 外部サービスの正常な応答を設定
        auth_mock.verify_job_access_permission.return_value = None
        processing_mock.get_job_status.return_value = {
            "status": "completed",
            "progress": 100,
            "original_request": {
                "num_speakers": 2,
                "detailed_output": False
            }
        }
        
        # Act（実行）
        result = await workflow.retrieve_job_status(job_identifier, user_context)
        
        # Assert（検証）
        assert result["job_id"] == job_identifier
        assert result["status"] == "completed"
        assert result["progress"] == 100
        assert result["result_available"] == True
        assert result["response_format"]["include_speaker_labels"] == True
        
        # 外部サービス呼び出し確認
        auth_mock.verify_job_access_permission.assert_called_once_with(job_identifier, user_context)
        processing_mock.get_job_status.assert_called_once_with(job_identifier)


# ==============================================================================
# Advanced Error Handling Tests
# ==============================================================================

@pytest.mark.error_scenarios
class TestWhisperAPIErrorHandling:
    """Whisper API エラーハンドリング高度テスト"""
    
    @pytest.mark.parametrize(
        ["error_scenario"],
        [
            ({
                "scenario_name": "認証失敗",
                "http_status": 401,
                "error_setup": "no_auth_header",
                "expected_message": "authentication.*required"
            }),
            ({
                "scenario_name": "無効フォーマット",
                "http_status": 400,
                "error_setup": "invalid_format",
                "expected_message": "無効な音声フォーマット"
            }),
            ({
                "scenario_name": "ファイルサイズ超過",
                "http_status": 413,
                "error_setup": "file_too_large",
                "expected_message": "ファイルサイズが大きすぎます"
            }),
            ({
                "scenario_name": "処理キュー満杯",
                "http_status": 429,
                "error_setup": "queue_full",
                "expected_message": "too.*many.*requests"
            }),
            ({
                "scenario_name": "ストレージサービス障害",
                "http_status": 503,
                "error_setup": "storage_unavailable",
                "expected_message": "service.*unavailable"
            }),
        ],
        ids=[
            "認証失敗_401エラー",
            "無効フォーマット_400エラー",
            "ファイルサイズ超過_413エラー",
            "処理キュー満杯_429エラー",
            "ストレージ障害_503エラー",
        ],
    )
    @pytest.mark.asyncio
    async def test_error_scenarios_各エラーケースで適切なレスポンス(
        self, async_test_client, error_scenario
    ):
        """各エラーシナリオで適切なHTTPステータスとメッセージを返すこと"""
        # Arrange（準備）
        factory = WhisperAPIDataFactory()
        
        if error_scenario["error_setup"] == "no_auth_header":
            # 認証ヘッダーなしでリクエスト
            upload_data = factory.create_upload_request_data()
            headers = {}  # Authorization ヘッダーなし
            
        elif error_scenario["error_setup"] == "invalid_format":
            upload_data = factory.create_upload_request_data(
                filename="document.pdf",
                content_type="application/pdf"
            )
            headers = {"Authorization": "Bearer test-token"}
            
        elif error_scenario["error_setup"] == "file_too_large":
            upload_data = factory.create_upload_request_data(
                filename="huge-file.wav"
            )
            headers = {"Authorization": "Bearer test-token"}
            
            # ファイルサイズが大きいGCSモック設定
            with patch("backend.app.api.whisper.get_file_info_from_gcs") as mock_file_info:
                mock_file_info.return_value = {
                    "size": 200 * 1024 * 1024,  # 200MB
                    "content_type": "audio/wav"
                }
                
        elif error_scenario["error_setup"] == "queue_full":
            upload_data = factory.create_upload_request_data()
            headers = {"Authorization": "Bearer test-token"}
            
            # 処理キューが満杯の状態をモック
            with patch("backend.app.api.whisper._get_current_processing_job_count", return_value=100), \
                 patch("backend.app.api.whisper._get_env_var", return_value="10"):  # 上限10
                pass
                
        elif error_scenario["error_setup"] == "storage_unavailable":
            upload_data = factory.create_upload_request_data()
            headers = {"Authorization": "Bearer test-token"}
            
            # ストレージサービス障害をモック
            with patch("backend.app.api.whisper.get_file_info_from_gcs", side_effect=Exception("Storage service unavailable")):
                pass
        
        # Act（実行）
        response = await async_test_client.post(
            "/backend/whisper",
            json=upload_data,
            headers=headers
        )
        
        # Assert（検証）
        assert response.status_code == error_scenario["http_status"]
        
        if response.status_code != 401:  # 401以外はJSONレスポンスを期待
            response_data = response.json()
            error_message = response_data.get("detail", "")
            
            import re
            assert re.search(error_scenario["expected_message"], error_message, re.IGNORECASE), \
                f"Expected pattern '{error_scenario['expected_message']}' not found in '{error_message}'"


# ==============================================================================
# Performance and Load Tests
# ==============================================================================

@pytest.mark.performance
class TestWhisperAPIPerformance:
    """Whisper API パフォーマンステスト"""
    
    @pytest.mark.asyncio
    async def test_contract_validation_performance_大量検証での性能(
        self, enhanced_test_metrics
    ):
        """契約検証ロジックの大量データでの性能テスト"""
        # Arrange（準備）
        enhanced_test_metrics.start_measurement()
        
        factory = WhisperAPIDataFactory()
        
        # 1000件のバリデーション要求を生成
        validation_requests = []
        for _ in range(1000):
            filename = f"{factory.fake.slug()}.{factory.fake.random_element(['wav', 'mp3', 'm4a', 'pdf', 'txt'])}"
            size = factory.fake.random_int(min=1000, max=200*1024*1024)
            validation_requests.append((filename, size))
        
        # Act（実行）
        validation_results = []
        for filename, size in validation_requests:
            format_result = WhisperAPIContractCore.validate_upload_request_format(filename)
            size_result = WhisperAPIContractCore.validate_file_size(size)
            validation_results.append((format_result, size_result))
        
        enhanced_test_metrics.end_measurement()
        
        # Assert（検証）
        assert len(validation_results) == 1000
        
        # 結果の統計確認
        valid_format_count = sum(1 for r in validation_results if r[0]["valid"])
        valid_size_count = sum(1 for r in validation_results if r[1]["valid"])
        
        # 有効/無効の比率が期待範囲内
        assert 400 <= valid_format_count <= 800  # 40-80%が有効フォーマット
        assert 700 <= valid_size_count <= 950    # 70-95%が有効サイズ
        
        # パフォーマンス閾値確認
        enhanced_test_metrics.assert_performance_thresholds(
            max_duration_seconds=2.0,   # 2秒以内
            max_memory_increase_mb=30.0  # 30MB増加以内
        )
    
    @pytest.mark.asyncio
    async def test_processing_time_estimation_performance_計算性能(
        self
    ):
        """処理時間推定計算の性能テスト"""
        # Arrange（準備）
        test_scenarios = []
        for _ in range(5000):
            file_size = random.randint(1024, 100*1024*1024)
            num_speakers = random.randint(1, 10)
            language = random.choice(["ja", "en", "auto", "zh", "ko"])
            test_scenarios.append((file_size, num_speakers, language))
        
        # Act（実行）
        start_time = time.time()
        
        estimation_results = []
        for file_size, num_speakers, language in test_scenarios:
            estimated_time = WhisperAPIContractCore.calculate_estimated_processing_time(
                file_size, num_speakers, language
            )
            estimation_results.append(estimated_time)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Assert（検証）
        assert len(estimation_results) == 5000
        assert all(t >= 10 for t in estimation_results)  # 全て最小10秒以上
        
        # パフォーマンス基準
        assert processing_time < 1.0  # 1秒以内
        calculations_per_second = len(test_scenarios) / processing_time
        assert calculations_per_second > 5000  # 5000計算/sec以上
        
        # 統計確認
        avg_estimation = sum(estimation_results) / len(estimation_results)
        max_estimation = max(estimation_results)
        min_estimation = min(estimation_results)
        
        assert 10 <= min_estimation <= 100
        assert 100 <= avg_estimation <= 3000
        assert 1000 <= max_estimation <= 10000
        
        print(f"推定計算性能: {calculations_per_second:.1f} calculations/sec")
        print(f"推定時間統計: min={min_estimation}s, avg={avg_estimation:.1f}s, max={max_estimation}s")


# ==============================================================================
# Test Data Factory Integration Tests
# ==============================================================================

class TestWhisperAPIDataFactoryIntegration:
    """Whisper API テストデータファクトリー統合テスト"""
    
    def test_factory_data_consistency_データ生成一貫性確保(self):
        """ファクトリーが一貫性のあるデータを生成することを確認"""
        # Arrange（準備）
        factory = WhisperAPIDataFactory()
        
        # Act（実行）
        # 同じシードで複数回生成
        data1 = [factory.create_upload_request_data() for _ in range(10)]
        
        # 新しいファクトリーインスタンス（同じシード）
        factory2 = WhisperAPIDataFactory()
        data2 = [factory2.create_upload_request_data() for _ in range(10)]
        
        # Assert（検証）
        # 再現可能性の確認
        for d1, d2 in zip(data1, data2):
            assert d1["filename"] == d2["filename"]
            assert d1["language"] == d2["language"]
            assert d1["num_speakers"] == d2["num_speakers"]
    
    def test_transcription_segments_quality_セグメント品質確認(self):
        """生成される文字起こしセグメントの品質を確認"""
        # Arrange（準備）
        factory = WhisperAPIDataFactory()
        
        # Act（実行）
        ja_segments = factory.create_realistic_transcription_segments(10, "ja")
        en_segments = factory.create_realistic_transcription_segments(10, "en")
        
        # Assert（検証）
        # 日本語セグメント品質確認
        assert len(ja_segments) == 10
        for segment in ja_segments:
            assert "start" in segment and "end" in segment
            assert "text" in segment and "speaker" in segment
            assert "confidence" in segment
            assert segment["start"] < segment["end"]
            assert 0.8 <= segment["confidence"] <= 1.0
            # 日本語文字が含まれているか
            assert any(ord(char) > 127 for char in segment["text"])
        
        # 英語セグメント品質確認
        assert len(en_segments) == 10
        for segment in en_segments:
            assert "start" in segment and "end" in segment
            assert "text" in segment and "speaker" in segment
            assert segment["start"] < segment["end"]
            # 英語として妥当な内容か（簡易チェック）
            assert "meeting" in segment["text"].lower() or "project" in segment["text"].lower() or "question" in segment["text"].lower()
        
        # タイムスタンプの連続性確認
        for i in range(len(ja_segments) - 1):
            assert ja_segments[i]["end"] <= ja_segments[i+1]["start"] + 1.0  # 1秒の重複まで許容
    
    def test_speaker_config_variations_設定バリエーション確認(self):
        """スピーカー設定バリエーションの妥当性を確認"""
        # Arrange（準備）
        factory = WhisperAPIDataFactory()
        
        # Act（実行）
        variations = factory.create_speaker_config_variations()
        
        # Assert（検証）
        assert len(variations) >= 4  # 最低4パターン
        
        # 各パターンの構造確認
        for i, config in enumerate(variations):
            assert isinstance(config, dict)
            assert len(config) >= 1  # 最低1人の話者
            
            for speaker_id, speaker_info in config.items():
                assert speaker_id.startswith("SPEAKER_")
                assert "name" in speaker_info
                assert "color" in speaker_info
                assert speaker_info["name"]  # 空でない名前
                assert speaker_info["color"].startswith("#")  # カラーコード形式
                assert len(speaker_info["color"]) == 7  # #RRGGBB
        
        # 単一話者、複数話者、多話者パターンが含まれることを確認
        speaker_counts = [len(config) for config in variations]
        assert min(speaker_counts) == 1  # 単一話者
        assert max(speaker_counts) >= 3  # 多話者


# ==============================================================================
# Advanced Mock Strategies for API Testing
# ==============================================================================

class TestWhisperAPIAdvancedMockStrategies:
    """Whisper API 高度なモック戦略のテスト例"""
    
    @pytest.mark.asyncio
    async def test_minimal_mocking_api_モック最小化API例(self, async_test_client, mock_auth_user):
        """API テストでモックを最小化し、実際の契約ロジックを可能な限りテストする例"""
        # Arrange（準備）
        # モックは本当に制御が困難な外部依存のみ
        factory = WhisperAPIDataFactory()
        upload_data = factory.create_upload_request_data(
            filename="minimal-mock-test.wav",
            num_speakers=2,
            language="ja"
        )
        
        # 制御困難な外部サービスのみモック
        with patch("backend.app.api.whisper.enqueue_job_atomic") as mock_enqueue, \
             patch("backend.app.api.whisper.get_file_info_from_gcs") as mock_file_info:
            
            # 正常なファイル情報を返すスタブ
            mock_file_info.return_value = {
                "size": 10 * 1024 * 1024,  # 10MB
                "content_type": "audio/wav"
            }
            mock_enqueue.return_value = None
            
            # Act（実行）
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            # Assert（検証）
            # 実際のビジネスロジックが動作したことを確認
            assert response.status_code == 200
            response_data = response.json()
            assert "job_id" in response_data
            assert "file_hash" in response_data
            
            # 契約検証ロジックが実際に動作したことの間接確認
            # （無効なフォーマットなら400エラーになるはず）
    
    @pytest.mark.asyncio
    async def test_behavior_verification_api_契約検証API例(self, async_test_client, mock_auth_user):
        """API で外部システムとの契約（振る舞い）を検証する例"""
        # Arrange（準備）
        factory = WhisperAPIDataFactory()
        upload_data = factory.create_upload_request_data(
            filename="behavior-verification.wav",
            description="重要な会議の録音",
            num_speakers=4,
            language="ja",
            tags=["urgent", "quarterly-meeting"]
        )
        
        # 外部システムとの契約を検証するためのモック
        with patch("backend.app.api.whisper.enqueue_job_atomic") as mock_enqueue, \
             patch("backend.app.api.whisper.get_file_info_from_gcs") as mock_file_info, \
             patch("backend.app.api.whisper.trigger_whisper_batch_processing") as mock_trigger:
            
            mock_file_info.return_value = {
                "size": 30 * 1024 * 1024,  # 30MB
                "content_type": "audio/wav"
            }
            mock_enqueue.return_value = None
            mock_trigger.return_value = None
            
            # Act（実行）
            response = await async_test_client.post(
                "/backend/whisper",
                json=upload_data,
                headers={"Authorization": "Bearer test-token"}
            )
            
            # Assert（検証）
            assert response.status_code == 200
            
            # 外部システムとの契約を確認
            mock_enqueue.assert_called_once()
            enqueue_call_args = mock_enqueue.call_args
            
            # エンキューされたジョブデータの検証
            job_data = enqueue_call_args[0][1]  # 第2引数がジョブデータ
            assert job_data["description"] == "重要な会議の録音"
            assert job_data["num_speakers"] == 4
            assert job_data["language"] == "ja"
            assert "urgent" in job_data["tags"]
            assert job_data["user_id"] == mock_auth_user["uid"]
            
            # ファイル情報取得の契約確認
            mock_file_info.assert_called_once()
            file_info_call_args = mock_file_info.call_args[0][0]
            assert file_info_call_args.startswith("gs://")  # GCSパス形式
            
            # バッチ処理トリガーの契約確認
            mock_trigger.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_autospec_pattern_api_autospecパターンAPI例(self):
        """create_autospec + side_effect パターンを API テストで適用する例"""
        # Arrange（準備）
        # 実際のクラスからautospecを作成
        from google.cloud import storage
        mock_storage_client_class = create_autospec(storage.Client, spec_set=True)
        
        # カスタム振る舞いを定義
        class APITestStorageBehavior:
            def __init__(self):
                self._file_info = {}
            
            def get_file_info(self, gcs_path: str) -> Dict[str, Any]:
                if not isinstance(gcs_path, str) or not gcs_path.startswith("gs://"):
                    raise ValueError("無効なGCSパス")
                
                # ファイル拡張子に基づく情報を返す
                if gcs_path.endswith(".wav"):
                    return {
                        "size": 15 * 1024 * 1024,
                        "content_type": "audio/wav",
                        "created": "2025-06-09T10:00:00Z"
                    }
                elif gcs_path.endswith(".pdf"):
                    return {
                        "size": 1 * 1024 * 1024,
                        "content_type": "application/pdf",
                        "created": "2025-06-09T10:00:00Z"
                    }
                else:
                    raise FileNotFoundError(f"ファイルが見つかりません: {gcs_path}")
        
        # autospecモックにカスタム振る舞いを注入
        behavior = APITestStorageBehavior()
        mock_storage_instance = mock_storage_client_class.return_value
        
        # side_effectでカスタム振る舞いを設定
        with patch("backend.app.api.whisper.get_file_info_from_gcs", side_effect=behavior.get_file_info):
            
            factory = WhisperAPIDataFactory()
            
            # Act & Assert（実行・検証）- 有効なケース
            valid_upload_data = factory.create_upload_request_data(filename="autospec-test.wav")
            
            # 注意: この例では実際のAPIを呼ばず、カスタム振る舞いの動作のみ確認
            file_info = behavior.get_file_info("gs://bucket/autospec-test.wav")
            assert file_info["content_type"] == "audio/wav"
            assert file_info["size"] == 15 * 1024 * 1024
            
            # Act & Assert（実行・検証）- 無効なケース
            with pytest.raises(ValueError, match="無効なGCSパス"):
                behavior.get_file_info("invalid-path")
            
            with pytest.raises(FileNotFoundError):
                behavior.get_file_info("gs://bucket/nonexistent.xyz")
            
            # PDFファイルのケース
            pdf_info = behavior.get_file_info("gs://bucket/document.pdf")
            assert pdf_info["content_type"] == "application/pdf"
            
            # autospecの安全性確認
            # ✅ 存在するメソッドのみ呼び出し可能
            assert hasattr(mock_storage_instance, 'bucket')
            # ❌ 存在しないメソッドは呼び出せない
            assert not hasattr(mock_storage_instance, 'non_existent_method')


if __name__ == "__main__":
    # テスト改善サマリー情報
    improvement_summary = {
        "refactoring_focus": [
            "テストダブル戦略の最適化（モック最小化、実オブジェクト優先）",
            "振る舞い検証 vs 実装詳細テストの明確な分離",
            "create_autospec + side_effect パターンの徹底適用",
            "包括的パラメータ化テストによるエッジケース検証"
        ],
        "behavioral_separation": {
            "core_logic": "WhisperAPIContractCore（契約検証、推定計算）",
            "workflow": "WhisperAPIServiceWorkflow（外部サービス連携）",
            "benefits": ["テスト容易性向上", "保守性向上", "ビジネスロジックの独立性"]
        },
        "test_improvements": {
            "contract_tests": "17個の包括的パラメータ化テスト",
            "workflow_tests": "代表的なエンドツーエンドフロー検証",
            "error_handling": "5種類のエラーシナリオ検証",
            "performance_tests": "大量データでの性能確認",
            "mock_strategies": "3種類の高度なモック戦略例"
        },
        "data_factory_features": [
            "Faker統合による現実的なデータ生成",
            "言語別（日本語・英語）の文字起こしセグメント",
            "多様なスピーカー設定パターン",
            "包括的エラーシナリオファクトリー"
        ]
    }
    
    print("=" * 80)
    print("Whisper API Refactored Testing Suite")
    print("=" * 80)
    for category, items in improvement_summary.items():
        print(f"\n{category.replace('_', ' ').title()}:")
        if isinstance(items, list):
            for item in items:
                print(f"  - {item}")
        elif isinstance(items, dict):
            for key, value in items.items():
                print(f"  {key}: {value}")
    print("=" * 80)
