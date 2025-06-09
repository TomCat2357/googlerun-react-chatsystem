"""
高度なパラメータ化テスト：複雑なシナリオとエッジケースの包括的検証
Advanced Parameterized Tests with Complex Scenarios

このテストファイルは、以下の高度なパラメータ化テスト戦略を実装します：
1. 多次元パラメータの組み合わせテスト
2. エッジケースと境界値の網羅的検証
3. 動的テストデータ生成
4. 条件付きパラメータテスト
5. カスタムパラメータIDによる可読性向上
"""

import pytest
import itertools
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional, Union
from faker import Faker
from unittest.mock import patch, MagicMock, create_autospec

# プロジェクト固有のインポート
from common_utils.class_types import WhisperFirestoreData


class TestAdvancedParameterizedScenarios:
    """高度なパラメータ化テストシナリオ"""
    
    @pytest.mark.parametrize(
        ["audio_format", "file_size_mb", "duration_minutes", "language", "num_speakers", "expected_outcome"],
        [
            # 基本的な有効パターン（同値分割）
            ("wav", 10, 5, "ja", 1, "success"),
            ("mp3", 15, 10, "en", 2, "success"),
            ("m4a", 20, 15, "auto", 3, "success"),
            
            # 境界値分析：ファイルサイズ
            ("wav", 0.1, 5, "ja", 1, "success"),      # 最小サイズ
            ("wav", 99.9, 5, "ja", 1, "success"),     # 上限以下
            ("wav", 100.0, 5, "ja", 1, "success"),    # 上限ちょうど
            ("wav", 100.1, 5, "ja", 1, "file_too_large"),  # 上限超過
            ("wav", 500, 5, "ja", 1, "file_too_large"),    # 大幅超過
            
            # 境界値分析：音声時間長
            ("wav", 10, 0.1, "ja", 1, "success"),       # 最短時間
            ("wav", 10, 29.9, "ja", 1, "success"),      # 上限以下
            ("wav", 10, 30.0, "ja", 1, "success"),      # 上限ちょうど
            ("wav", 10, 30.1, "ja", 1, "duration_too_long"),  # 上限超過
            ("wav", 10, 60, "ja", 1, "duration_too_long"),    # 大幅超過
            
            # 境界値分析：話者数
            ("wav", 10, 5, "ja", 0, "invalid_speakers"),    # 無効な話者数
            ("wav", 10, 5, "ja", 1, "success"),             # 最小話者数
            ("wav", 10, 5, "ja", 10, "success"),            # 最大話者数
            ("wav", 10, 5, "ja", 11, "too_many_speakers"),  # 上限超過
            
            # 言語とフォーマットの組み合わせ
            ("wav", 10, 5, "zh", 1, "success"),    # 中国語
            ("wav", 10, 5, "ko", 1, "success"),    # 韓国語
            ("wav", 10, 5, "fr", 1, "success"),    # フランス語
            ("wav", 10, 5, "invalid_lang", 1, "unsupported_language"),
            
            # 複合エラーケース
            ("txt", 10, 5, "ja", 1, "invalid_format"),      # 無効フォーマット
            ("wav", 200, 60, "invalid", 15, "multiple_errors"),  # 複数エラー
            ("", 10, 5, "ja", 1, "missing_format"),         # フォーマット欠落
        ],
        ids=[
            # 基本パターン
            "WAV_10MB_5分_日本語_1話者_正常",
            "MP3_15MB_10分_英語_2話者_正常",
            "M4A_20MB_15分_自動_3話者_正常",
            
            # ファイルサイズ境界値
            "WAV_最小サイズ_正常",
            "WAV_上限以下_正常", 
            "WAV_上限ちょうど_正常",
            "WAV_上限超過_ファイル過大",
            "WAV_大幅超過_ファイル過大",
            
            # 時間長境界値
            "WAV_最短時間_正常",
            "WAV_時間上限以下_正常",
            "WAV_時間上限ちょうど_正常", 
            "WAV_時間上限超過_時間過長",
            "WAV_時間大幅超過_時間過長",
            
            # 話者数境界値
            "WAV_話者数0_無効話者数",
            "WAV_最小話者数_正常",
            "WAV_最大話者数_正常",
            "WAV_話者数上限超過_話者数過多",
            
            # 言語バリエーション
            "WAV_中国語_正常",
            "WAV_韓国語_正常",
            "WAV_フランス語_正常",
            "WAV_無効言語_未対応言語",
            
            # エラーケース
            "TXT_無効フォーマット",
            "複合エラー_全条件違反",
            "フォーマット欠落_エラー",
        ]
    )
    def test_audio_upload_validation_comprehensive_scenarios(
        self, audio_format, file_size_mb, duration_minutes, language, num_speakers, expected_outcome
    ):
        """音声アップロードバリデーションの包括的シナリオテスト"""
        # Arrange（準備）
        upload_request = {
            "filename": f"test_audio.{audio_format}" if audio_format else "test_audio",
            "file_size_bytes": int(file_size_mb * 1024 * 1024),
            "duration_seconds": duration_minutes * 60,
            "language": language,
            "num_speakers": num_speakers,
            "audio_data": f"mock_audio_data_{uuid.uuid4().hex[:8]}"
        }
        
        # Act（実行）
        result = self._simulate_upload_validation(upload_request)
        
        # Assert（検証）
        assert result["outcome"] == expected_outcome, (
            f"Expected outcome '{expected_outcome}' for {audio_format} "
            f"({file_size_mb}MB, {duration_minutes}min, {language}, {num_speakers} speakers), "
            f"got '{result['outcome']}'. Details: {result.get('details', 'N/A')}"
        )
        
        # 追加の詳細検証
        if expected_outcome == "success":
            assert result["validated_data"] is not None
            assert result["validated_data"]["language"] == language
        else:
            assert "error_message" in result
            assert len(result["error_message"]) > 0
    
    def _simulate_upload_validation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """音声アップロードバリデーションのシミュレーション"""
        errors = []
        
        # フォーマット検証
        if not request.get("filename") or not request["filename"]:
            errors.append("ファイル名が必要です")
        elif "." not in request["filename"]:
            errors.append("ファイル拡張子が必要です")
        else:
            extension = request["filename"].split(".")[-1].lower()
            if extension not in ["wav", "mp3", "m4a"]:
                errors.append(f"未対応のファイル形式: {extension}")
        
        # サイズ検証
        if request.get("file_size_bytes", 0) > 100 * 1024 * 1024:  # 100MB
            errors.append("ファイルサイズが上限（100MB）を超過しています")
        
        # 時間長検証  
        if request.get("duration_seconds", 0) > 30 * 60:  # 30分
            errors.append("音声時間が上限（30分）を超過しています")
        
        # 話者数検証
        if request.get("num_speakers", 0) <= 0:
            errors.append("話者数は1以上である必要があります")
        elif request.get("num_speakers", 0) > 10:
            errors.append("話者数が上限（10人）を超過しています")
        
        # 言語検証
        supported_languages = {"ja", "en", "zh", "ko", "fr", "auto"}
        if request.get("language") not in supported_languages:
            errors.append(f"未対応の言語: {request.get('language')}")
        
        # 結果判定
        if not errors:
            return {
                "outcome": "success",
                "validated_data": request,
                "details": "バリデーション成功"
            }
        elif len(errors) > 1:
            return {
                "outcome": "multiple_errors",
                "error_message": "; ".join(errors),
                "details": f"{len(errors)}個のエラーが検出されました"
            }
        else:
            # 単一エラーの場合、具体的なアウトカムを決定
            error_msg = errors[0]
            if "ファイル形式" in error_msg or "拡張子" in error_msg or "ファイル名" in error_msg:
                outcome = "invalid_format" if "形式" in error_msg else "missing_format"
            elif "ファイルサイズ" in error_msg:
                outcome = "file_too_large"
            elif "音声時間" in error_msg:
                outcome = "duration_too_long"
            elif "話者数" in error_msg:
                outcome = "invalid_speakers" if "1以上" in error_msg else "too_many_speakers"
            elif "言語" in error_msg:
                outcome = "unsupported_language"
            else:
                outcome = "unknown_error"
            
            return {
                "outcome": outcome,
                "error_message": error_msg,
                "details": "バリデーションエラー"
            }


class TestDynamicParameterGeneration:
    """動的パラメータ生成とFaker統合テスト"""
    
    @pytest.fixture
    def dynamic_test_data_generator(self):
        """動的テストデータ生成器"""
        fake = Faker(['ja_JP', 'en_US'])
        fake.seed_instance(42)  # 再現可能なテスト
        
        def generate_whisper_job_scenarios(count: int = 20) -> List[Tuple]:
            """Whisperジョブの多様なシナリオを動的生成"""
            scenarios = []
            
            for i in range(count):
                # ランダムだが制御された条件生成
                status = fake.random_element(["queued", "processing", "completed", "failed"])
                
                # 条件に応じたテストデータ調整
                if status == "completed":
                    # 完了ジョブは現実的なデータ
                    audio_duration = fake.random_int(5000, 600000)  # 5秒～10分
                    audio_size = fake.random_int(100000, 5000000)   # 100KB～5MB
                    error_message = None
                elif status == "failed":
                    # 失敗ジョブはエラー情報付き
                    audio_duration = fake.random_int(1, 10000)  # 短時間or問題のある長さ
                    audio_size = fake.random_int(1, 200000000)  # 極端なサイズ
                    error_message = fake.random_element([
                        "音声ファイルが破損しています",
                        "処理時間が上限を超過しました", 
                        "メモリ不足により処理に失敗しました",
                        "未対応の音声形式です"
                    ])
                else:
                    # 進行中/待機中ジョブは標準的
                    audio_duration = fake.random_int(10000, 1800000)  # 10秒～30分
                    audio_size = fake.random_int(500000, 50000000)    # 500KB～50MB
                    error_message = None
                
                scenario = (
                    f"job_{i:03d}",  # job_id
                    status,
                    audio_duration,
                    audio_size,
                    fake.random_element(["ja", "en", "auto"]),  # language
                    fake.random_int(1, 5),  # num_speakers
                    error_message,
                    fake.boolean(chance_of_getting_true=30)  # has_speaker_diarization
                )
                scenarios.append(scenario)
            
            return scenarios
        
        return generate_whisper_job_scenarios
    
    def test_whisper_job_state_transitions_dynamic_scenarios(
        self, dynamic_test_data_generator, enhanced_gcp_services
    ):
        """動的生成シナリオによるWhisperジョブ状態遷移テスト"""
        # Arrange（準備）
        scenarios = dynamic_test_data_generator(count=10)
        
        for job_id, status, duration, size, language, speakers, error_msg, has_diarization in scenarios:
            # Act（実行）
            job_data = WhisperFirestoreData(
                job_id=job_id,
                user_id="test-user",
                user_email="test@example.com",
                filename=f"{job_id}_audio.wav",
                gcs_bucket_name="test-bucket",
                audio_size=size,
                audio_duration_ms=duration,
                file_hash=f"hash_{job_id}",
                status=status,
                num_speakers=speakers,
                min_speakers=1,
                max_speakers=speakers,
                language=language,
                error_message=error_msg,
                speaker_diarization=has_diarization
            )
            
            # 状態遷移ロジックをテスト
            result = self._simulate_job_state_validation(job_data)
            
            # Assert（検証）
            if status == "completed":
                assert result["is_valid_completed_job"]
                assert result["processing_time"] is not None
            elif status == "failed":
                assert not result["is_valid_completed_job"]
                assert result["error_category"] is not None
            else:
                assert result["can_transition_to_processing"]
    
    def _simulate_job_state_validation(self, job_data: WhisperFirestoreData) -> Dict[str, Any]:
        """ジョブ状態バリデーションのシミュレーション"""
        result = {
            "is_valid_completed_job": False,
            "can_transition_to_processing": False,
            "processing_time": None,
            "error_category": None
        }
        
        if job_data.status == "completed":
            # 完了ジョブの妥当性検証
            if job_data.audio_duration_ms > 1000 and job_data.audio_size > 10000:
                result["is_valid_completed_job"] = True
                result["processing_time"] = job_data.audio_duration_ms / 1000  # 秒単位
        
        elif job_data.status == "failed":
            # 失敗ジョブのエラー分類
            if job_data.error_message:
                if "破損" in job_data.error_message:
                    result["error_category"] = "corruption"
                elif "時間" in job_data.error_message or "上限" in job_data.error_message:
                    result["error_category"] = "timeout"
                elif "メモリ" in job_data.error_message:
                    result["error_category"] = "resource"
                else:
                    result["error_category"] = "format"
        
        elif job_data.status in ["queued", "processing"]:
            # 処理可能性の検証
            if (job_data.audio_size < 100 * 1024 * 1024 and  # 100MB未満
                job_data.audio_duration_ms < 30 * 60 * 1000):  # 30分未満
                result["can_transition_to_processing"] = True
        
        return result


class TestConditionalParameterization:
    """条件付きパラメータ化テスト"""
    
    @pytest.mark.parametrize("language", ["ja", "en", "zh", "ko"])
    @pytest.mark.parametrize("model_size", ["base", "small", "medium", "large"])
    @pytest.mark.parametrize("audio_quality", ["low", "standard", "high"])
    def test_whisper_model_performance_matrix(self, language, model_size, audio_quality):
        """言語×モデルサイズ×音質の性能マトリックステスト"""
        # 特定の組み合わせをスキップ（現実的でない組み合わせ）
        if language == "zh" and model_size == "base":
            pytest.skip("中国語は基本モデルでは精度が不十分")
        
        if audio_quality == "low" and model_size == "large":
            pytest.skip("低音質音声に大型モデルは非効率")
        
        # Arrange（準備）
        model_config = {
            "language": language,
            "model_size": model_size,
            "audio_quality": audio_quality
        }
        
        # Act（実行）
        performance_metrics = self._simulate_model_performance(model_config)
        
        # Assert（検証）
        # 言語特有の期待値
        if language == "ja":
            assert performance_metrics["accuracy"] > 0.85  # 日本語は高精度期待
        elif language == "en":
            assert performance_metrics["accuracy"] > 0.90  # 英語は最高精度
        
        # モデルサイズ特有の期待値
        if model_size == "large":
            assert performance_metrics["processing_time"] > 5.0  # 大型モデルは時間かかる
            assert performance_metrics["accuracy"] > 0.88  # 高精度
        elif model_size == "base":
            assert performance_metrics["processing_time"] < 2.0  # 高速
        
        # 音質特有の期待値
        if audio_quality == "high":
            assert performance_metrics["preprocessing_time"] < 1.0  # 前処理高速
        elif audio_quality == "low":
            assert performance_metrics["preprocessing_time"] > 2.0  # 前処理に時間
    
    def _simulate_model_performance(self, config: Dict[str, str]) -> Dict[str, float]:
        """モデル性能シミュレーション"""
        # 基本性能値
        base_accuracy = 0.80
        base_processing_time = 3.0
        base_preprocessing_time = 1.5
        
        # 言語による調整
        language_factors = {
            "ja": {"accuracy": 1.05, "processing": 1.1},
            "en": {"accuracy": 1.12, "processing": 1.0},
            "zh": {"accuracy": 0.95, "processing": 1.2},
            "ko": {"accuracy": 1.00, "processing": 1.15}
        }
        
        # モデルサイズによる調整
        model_factors = {
            "base": {"accuracy": 0.95, "processing": 0.6},
            "small": {"accuracy": 1.0, "processing": 0.8},
            "medium": {"accuracy": 1.05, "processing": 1.2},
            "large": {"accuracy": 1.15, "processing": 1.8}
        }
        
        # 音質による調整
        quality_factors = {
            "low": {"accuracy": 0.88, "preprocessing": 2.5},
            "standard": {"accuracy": 1.0, "preprocessing": 1.0},
            "high": {"accuracy": 1.08, "preprocessing": 0.7}
        }
        
        lang_factor = language_factors[config["language"]]
        model_factor = model_factors[config["model_size"]]
        quality_factor = quality_factors[config["audio_quality"]]
        
        return {
            "accuracy": base_accuracy * lang_factor["accuracy"] * model_factor["accuracy"] * quality_factor["accuracy"],
            "processing_time": base_processing_time * lang_factor["processing"] * model_factor["processing"],
            "preprocessing_time": base_preprocessing_time * quality_factor["preprocessing"]
        }


class TestCombinationTestingPatterns:
    """組み合わせテストパターン（ペアワイズテスト）"""
    
    def test_pairwise_parameter_coverage(self):
        """ペアワイズテストによる効率的なパラメータカバレッジ"""
        # パラメータ定義
        audio_formats = ["wav", "mp3", "m4a"]
        languages = ["ja", "en", "auto"]
        speakers = [1, 2, 5]
        qualities = ["standard", "high"]
        
        # 全組み合わせは 3×3×3×2 = 54通り
        # ペアワイズなら大幅削減可能
        
        # 簡易ペアワイズ生成（実際のプロダクトではallpairspy等を使用）
        pairwise_combinations = [
            ("wav", "ja", 1, "standard"),
            ("wav", "en", 2, "high"),
            ("wav", "auto", 5, "standard"),
            ("mp3", "ja", 2, "high"),
            ("mp3", "en", 5, "standard"),
            ("mp3", "auto", 1, "high"),
            ("m4a", "ja", 5, "high"),
            ("m4a", "en", 1, "standard"),
            ("m4a", "auto", 2, "standard"),
        ]
        
        for format_val, lang_val, speaker_val, quality_val in pairwise_combinations:
            # 各組み合わせをテスト
            config = {
                "format": format_val,
                "language": lang_val,
                "speakers": speaker_val,
                "quality": quality_val
            }
            
            result = self._validate_configuration_compatibility(config)
            assert result["is_compatible"], f"Incompatible configuration: {config}"
    
    def _validate_configuration_compatibility(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """設定互換性の検証"""
        incompatibilities = []
        
        # 互換性ルールの検証
        if config["format"] == "m4a" and config["speakers"] > 3:
            incompatibilities.append("M4A形式は3話者を超える分離に対応していません")
        
        if config["language"] == "auto" and config["quality"] == "high":
            incompatibilities.append("自動言語検出は高品質モードでの精度が安定しません")
        
        return {
            "is_compatible": len(incompatibilities) == 0,
            "incompatibilities": incompatibilities
        }


class TestTemporalParameterPatterns:
    """時系列・時間軸パラメータのテストパターン"""
    
    @pytest.mark.parametrize(
        ["created_time_offset_hours", "updated_time_offset_hours", "current_status", "expected_state"],
        [
            # 正常な時系列パターン
            (-2, -1, "completed", "recently_completed"),    # 2時間前作成、1時間前完了
            (-24, -22, "completed", "daily_completed"),     # 24時間前作成、22時間前完了
            (-168, -1, "completed", "weekly_completed"),    # 1週間前作成、1時間前完了
            
            # 異常な時系列パターン
            (-1, -2, "processing", "invalid_timeline"),     # 作成後に更新時刻が過去
            (-168, -169, "failed", "invalid_timeline"),     # 更新時刻が作成時刻より古い
            
            # 長期間処理中のパターン
            (-25, -24, "processing", "stale_processing"),   # 24時間以上処理中
            (-169, -168, "processing", "very_stale"),       # 1週間以上処理中
            
            # 最近のアクティビティ
            (-0.5, -0.25, "processing", "active_processing"), # 30分前作成、15分前更新
            (-0.1, -0.05, "queued", "fresh_job"),           # 6分前作成、3分前更新
        ],
        ids=[
            "2時間前作成_1時間前完了_正常",
            "24時間前作成_22時間前完了_正常",
            "1週間前作成_1時間前完了_正常",
            "時系列不整合_作成後更新",
            "時系列不整合_更新が作成より古い",
            "24時間超過処理中_古い処理",
            "1週間超過処理中_非常に古い",
            "30分前作成_処理中_アクティブ",
            "6分前作成_待機中_新鮮",
        ]
    )
    def test_whisper_job_temporal_state_analysis(
        self, created_time_offset_hours, updated_time_offset_hours, current_status, expected_state
    ):
        """Whisperジョブの時系列状態分析テスト"""
        # Arrange（準備）
        now = datetime.now()
        created_at = now + timedelta(hours=created_time_offset_hours)
        updated_at = now + timedelta(hours=updated_time_offset_hours)
        
        job_data = {
            "job_id": f"temporal_test_{uuid.uuid4().hex[:8]}",
            "status": current_status,
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat()
        }
        
        # Act（実行）
        state_analysis = self._analyze_temporal_job_state(job_data, now)
        
        # Assert（検証）
        assert state_analysis["state"] == expected_state, (
            f"Expected temporal state '{expected_state}' for job created {created_time_offset_hours}h ago, "
            f"updated {updated_time_offset_hours}h ago, status '{current_status}', "
            f"got '{state_analysis['state']}'"
        )
        
        # 時系列不整合の場合は警告フラグが立つ
        if expected_state == "invalid_timeline":
            assert state_analysis["has_timeline_issues"]
            assert len(state_analysis["timeline_warnings"]) > 0
        
        # 古い処理の場合はアラートフラグが立つ
        if "stale" in expected_state:
            assert state_analysis["requires_attention"]
            assert state_analysis["staleness_hours"] > 24
    
    def _analyze_temporal_job_state(self, job_data: Dict[str, Any], current_time: datetime) -> Dict[str, Any]:
        """ジョブの時系列状態分析"""
        created_at = datetime.fromisoformat(job_data["created_at"])
        updated_at = datetime.fromisoformat(job_data["updated_at"])
        
        created_hours_ago = (current_time - created_at).total_seconds() / 3600
        updated_hours_ago = (current_time - updated_at).total_seconds() / 3600
        
        # 時系列整合性チェック
        timeline_issues = []
        if updated_at < created_at:
            timeline_issues.append("更新時刻が作成時刻より古い")
        
        # 状態判定
        if timeline_issues:
            state = "invalid_timeline"
        elif job_data["status"] == "processing":
            if updated_hours_ago > 168:  # 1週間
                state = "very_stale"
            elif updated_hours_ago > 24:  # 24時間
                state = "stale_processing"
            else:
                state = "active_processing"
        elif job_data["status"] == "completed":
            if created_hours_ago <= 3:
                state = "recently_completed"
            elif created_hours_ago <= 24:
                state = "daily_completed"
            else:
                state = "weekly_completed"
        elif job_data["status"] == "queued":
            if created_hours_ago <= 0.5:
                state = "fresh_job"
            else:
                state = "aged_queue"
        else:
            state = "unknown_state"
        
        return {
            "state": state,
            "has_timeline_issues": len(timeline_issues) > 0,
            "timeline_warnings": timeline_issues,
            "requires_attention": "stale" in state,
            "staleness_hours": max(created_hours_ago, updated_hours_ago),
            "created_hours_ago": created_hours_ago,
            "updated_hours_ago": updated_hours_ago
        }


# カスタムパラメータ化ヘルパー
def generate_realistic_file_scenarios():
    """現実的なファイルシナリオの生成"""
    scenarios = []
    
    # 小さなファイル
    scenarios.extend([
        ("short_meeting_recording.wav", 2, 30, "ja", 2),
        ("voice_memo.m4a", 1, 15, "en", 1),
        ("interview_snippet.mp3", 3, 60, "auto", 2)
    ])
    
    # 中程度のファイル
    scenarios.extend([
        ("conference_call.wav", 25, 600, "en", 5),
        ("lecture_recording.mp3", 35, 900, "ja", 1),
        ("panel_discussion.m4a", 40, 1200, "auto", 4)
    ])
    
    # 大きなファイル
    scenarios.extend([
        ("full_day_seminar.wav", 80, 2400, "ja", 3),
        ("workshop_recording.mp3", 95, 2700, "en", 6),
        ("long_interview.m4a", 90, 2500, "auto", 2)
    ])
    
    return scenarios


@pytest.mark.parametrize(
    ["filename", "size_mb", "duration_seconds", "language", "num_speakers"],
    generate_realistic_file_scenarios(),
    ids=lambda val: val[0] if isinstance(val, tuple) else str(val)  # ファイル名をテストIDに使用
)
def test_realistic_file_processing_scenarios(filename, size_mb, duration_seconds, language, num_speakers):
    """現実的なファイル処理シナリオテスト"""
    # このテストは generate_realistic_file_scenarios() で生成された
    # 現実的なファイルシナリオを使用
    
    file_data = {
        "filename": filename,
        "size_mb": size_mb,
        "duration_seconds": duration_seconds,
        "language": language,
        "num_speakers": num_speakers
    }
    
    # ファイル処理の妥当性検証
    processing_estimate = _estimate_processing_requirements(file_data)
    
    # 現実的な制約の確認
    assert processing_estimate["estimated_time_minutes"] > 0
    assert processing_estimate["memory_requirement_mb"] > 0
    assert processing_estimate["is_processable"]


def _estimate_processing_requirements(file_data: Dict[str, Any]) -> Dict[str, Any]:
    """ファイル処理要件の推定"""
    # 基本処理時間：音声1分あたり30秒の処理時間
    base_processing_minutes = file_data["duration_seconds"] / 60 * 0.5
    
    # 話者数による調整
    speaker_multiplier = 1.0 + (file_data["num_speakers"] - 1) * 0.2
    
    # メモリ要件：ファイルサイズの3倍程度
    memory_requirement = file_data["size_mb"] * 3
    
    # 処理可能性判定
    is_processable = (
        file_data["size_mb"] <= 100 and
        file_data["duration_seconds"] <= 1800 and
        file_data["num_speakers"] <= 10
    )
    
    return {
        "estimated_time_minutes": base_processing_minutes * speaker_multiplier,
        "memory_requirement_mb": memory_requirement,
        "is_processable": is_processable,
        "processing_complexity": "low" if file_data["num_speakers"] <= 2 else "high"
    }


if __name__ == "__main__":
    # テストファイルを直接実行する場合の設定
    pytest.main([__file__, "-v", "--tb=short", "-x"])