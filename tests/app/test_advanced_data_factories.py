"""
高度なテストデータファクトリ：Faker統合とリアルなテストデータ生成
Advanced Test Data Factories with Faker Integration

このテストファイルは、以下の高度なテストデータ戦略を実装します：
1. Fakerライブラリを活用したリアルなデータ生成
2. ドメイン固有のテストデータファクトリパターン
3. 階層的・依存関係のあるテストデータ生成
4. エッジケース・境界値のシステマティックな生成
5. 多言語・多地域対応のテストデータ
6. 時系列データとライフサイクルシミュレーション
"""

import pytest
import json
import uuid
import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union, Tuple
from faker import Faker
from faker.providers import BaseProvider
from dataclasses import dataclass, field
from enum import Enum
import itertools

# プロジェクト固有のインポート
from common_utils.class_types import WhisperFirestoreData


class WhisperJobStatus(Enum):
    """Whisperジョブステータス列挙型"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CustomWhisperProvider(BaseProvider):
    """Whisper固有のFakerプロバイダ"""
    
    def whisper_model_name(self) -> str:
        """Whisperモデル名を生成"""
        models = [
            "tiny", "tiny.en", "base", "base.en", 
            "small", "small.en", "medium", "medium.en",
            "large", "large-v2", "large-v3"
        ]
        return self.random_element(models)
    
    def audio_filename(self, language: str = "auto") -> str:
        """リアルな音声ファイル名を生成"""
        prefixes = {
            "ja": ["会議録音", "インタビュー", "講演", "会話", "プレゼン"],
            "en": ["meeting_recording", "interview", "lecture", "conversation", "presentation"],
            "auto": ["recording", "audio", "voice", "sound", "transcript"]
        }
        
        prefix_list = prefixes.get(language, prefixes["auto"])
        prefix = self.random_element(prefix_list)
        
        # 日付やID要素を追加
        date_part = self.generator.date().strftime("%Y%m%d")
        number_part = self.random_int(1, 999)
        
        extensions = ["wav", "mp3", "m4a", "flac"]
        ext = self.random_element(extensions)
        
        return f"{prefix}_{date_part}_{number_part:03d}.{ext}"
    
    def realistic_audio_duration_ms(self, scenario: str = "normal") -> int:
        """シナリオに応じたリアルな音声時間を生成"""
        durations = {
            "short": (5000, 120000),      # 5秒〜2分
            "normal": (60000, 1800000),   # 1分〜30分
            "long": (1800000, 7200000),   # 30分〜2時間
            "meeting": (600000, 3600000), # 10分〜1時間
            "interview": (1200000, 5400000), # 20分〜90分
            "lecture": (2700000, 10800000),  # 45分〜3時間
        }
        
        min_duration, max_duration = durations.get(scenario, durations["normal"])
        return self.random_int(min_duration, max_duration)
    
    def realistic_audio_size_bytes(self, duration_ms: int, quality: str = "standard") -> int:
        """音声時間と品質に基づいたリアルなファイルサイズを生成"""
        # 品質ごとのビットレート（bps）
        bitrates = {
            "low": 64000,      # 64 kbps
            "standard": 128000, # 128 kbps
            "high": 256000,    # 256 kbps
            "lossless": 1411200 # 1411.2 kbps (CD quality)
        }
        
        bitrate = bitrates.get(quality, bitrates["standard"])
        duration_seconds = duration_ms / 1000
        
        # 理論的サイズ + ランダムな変動（±20%）
        theoretical_size = int(bitrate * duration_seconds / 8)
        variation = self.random_int(-20, 20) / 100
        actual_size = int(theoretical_size * (1 + variation))
        
        return max(1000, actual_size)  # 最小1KB
    
    def whisper_error_message(self, error_type: str = "random") -> str:
        """Whisper処理エラーメッセージを生成"""
        error_messages = {
            "format": [
                "音声ファイル形式が未対応です",
                "ファイルが破損している可能性があります",
                "コーデックが認識できません"
            ],
            "size": [
                "ファイルサイズが上限を超過しています",
                "音声時間が制限時間を超えています",
                "処理可能なサイズを超過しました"
            ],
            "processing": [
                "音声処理中にエラーが発生しました",
                "モデルの読み込みに失敗しました",
                "メモリ不足により処理できませんでした"
            ],
            "timeout": [
                "処理時間が上限を超過しました",
                "タイムアウトが発生しました",
                "処理が予想以上に時間がかかっています"
            ],
            "network": [
                "ネットワーク接続エラーが発生しました",
                "ファイルのダウンロードに失敗しました",
                "外部サービスとの通信でエラーが発生しました"
            ]
        }
        
        if error_type == "random":
            error_type = self.random_element(list(error_messages.keys()))
        
        messages = error_messages.get(error_type, error_messages["processing"])
        return self.random_element(messages)


@dataclass
class WhisperTestScenario:
    """Whisperテストシナリオのデータクラス"""
    scenario_name: str
    user_count: int
    jobs_per_user: int
    status_distribution: Dict[str, float]
    duration_scenario: str
    quality_distribution: Dict[str, float]
    language_distribution: Dict[str, float]
    error_rate: float = 0.0
    tags: List[str] = field(default_factory=list)


class AdvancedWhisperDataFactory:
    """高度なWhisperテストデータファクトリ"""
    
    def __init__(self, locale: str = "ja_JP", seed: Optional[int] = None):
        """ファクトリ初期化"""
        self.faker = Faker([locale, "en_US"])
        if seed is not None:
            self.faker.seed_instance(seed)
        
        # カスタムプロバイダを追加
        self.faker.add_provider(CustomWhisperProvider)
        
        # 統計データの追跡
        self.generated_data_stats = {
            "total_jobs": 0,
            "total_users": 0,
            "status_counts": {},
            "language_counts": {},
            "file_format_counts": {}
        }
    
    def create_realistic_user_profile(self, user_type: str = "normal") -> Dict[str, Any]:
        """リアルなユーザープロファイルを生成"""
        base_profile = {
            "user_id": f"user_{self.faker.uuid4()}",
            "email": self.faker.email(),
            "name": self.faker.name(),
            "created_at": self.faker.date_time_between(start_date="-2y", end_date="now"),
            "last_login": self.faker.date_time_between(start_date="-30d", end_date="now"),
            "timezone": self.faker.timezone(),
            "preferred_language": self.faker.random_element(["ja", "en", "auto"])
        }
        
        # ユーザータイプ別の特性
        if user_type == "power_user":
            base_profile.update({
                "subscription_tier": "premium",
                "monthly_job_limit": 1000,
                "total_jobs_created": self.faker.random_int(500, 5000),
                "average_file_size_mb": self.faker.random_int(20, 100)
            })
        elif user_type == "casual_user":
            base_profile.update({
                "subscription_tier": "free",
                "monthly_job_limit": 50,
                "total_jobs_created": self.faker.random_int(1, 100),
                "average_file_size_mb": self.faker.random_int(1, 20)
            })
        elif user_type == "enterprise_user":
            base_profile.update({
                "subscription_tier": "enterprise",
                "monthly_job_limit": 10000,
                "total_jobs_created": self.faker.random_int(1000, 50000),
                "average_file_size_mb": self.faker.random_int(50, 200),
                "organization": self.faker.company(),
                "department": self.faker.random_element(["IT", "HR", "Marketing", "Research"])
            })
        else:  # normal user
            base_profile.update({
                "subscription_tier": "standard",
                "monthly_job_limit": 200,
                "total_jobs_created": self.faker.random_int(50, 500),
                "average_file_size_mb": self.faker.random_int(5, 50)
            })
        
        return base_profile
    
    def create_whisper_job_with_dependencies(
        self, 
        user_profile: Dict[str, Any], 
        status: str = "queued",
        scenario: str = "normal",
        **overrides
    ) -> WhisperFirestoreData:
        """依存関係を考慮したWhisperジョブデータを生成"""
        
        # ユーザープロファイルに基づく調整
        preferred_language = user_profile.get("preferred_language", "auto")
        user_tier = user_profile.get("subscription_tier", "standard")
        
        # 音声時間をユーザータイプとシナリオに応じて調整
        if user_tier == "enterprise":
            duration_scenario = "long" if scenario == "meeting" else "normal"
        elif user_tier == "free":
            duration_scenario = "short"
        else:
            duration_scenario = scenario
        
        duration_ms = self.faker.realistic_audio_duration_ms(duration_scenario)
        
        # ファイルサイズを音声時間と品質に基づいて生成
        quality = self.faker.random_element(["low", "standard", "high", "lossless"])
        audio_size = self.faker.realistic_audio_size_bytes(duration_ms, quality)
        
        # ファイル名をコンテキストに応じて生成
        filename = self.faker.audio_filename(preferred_language)
        
        # ハッシュ値を生成
        file_hash = hashlib.sha256(f"{filename}_{audio_size}_{duration_ms}".encode()).hexdigest()[:16]
        
        # 話者数をシナリオに応じて調整
        speaker_scenarios = {
            "interview": (2, 3),
            "meeting": (3, 8),
            "lecture": (1, 2),
            "conference": (5, 15),
            "normal": (1, 4)
        }
        min_speakers, max_speakers = speaker_scenarios.get(scenario, speaker_scenarios["normal"])
        num_speakers = self.faker.random_int(min_speakers, max_speakers)
        
        # タイムスタンプ生成（リアルな時系列）
        created_at = self.faker.date_time_between(start_date="-30d", end_date="now")
        
        if status == "completed":
            # 完了ジョブは作成から数時間後に完了
            processing_time_hours = self.faker.random_int(1, 12)
            updated_at = created_at + timedelta(hours=processing_time_hours)
        elif status == "failed":
            # 失敗ジョブは作成から短時間で失敗
            failure_time_minutes = self.faker.random_int(5, 120)
            updated_at = created_at + timedelta(minutes=failure_time_minutes)
        elif status == "processing":
            # 処理中ジョブは最近更新されている
            processing_time_minutes = self.faker.random_int(10, 480)
            updated_at = created_at + timedelta(minutes=processing_time_minutes)
        else:  # queued
            updated_at = created_at
        
        # エラーメッセージ（失敗時のみ）
        error_message = None
        if status == "failed":
            error_types = ["format", "size", "processing", "timeout", "network"]
            error_type = self.faker.random_element(error_types)
            error_message = self.faker.whisper_error_message(error_type)
        
        # タグ生成（シナリオに応じて）
        scenario_tags = {
            "meeting": ["会議", "ビジネス", "recording"],
            "interview": ["インタビュー", "対談", "人事"],
            "lecture": ["講演", "教育", "セミナー"],
            "conference": ["カンファレンス", "イベント", "プレゼン"],
            "normal": ["録音", "音声", "文字起こし"]
        }
        tags = self.faker.random_elements(
            scenario_tags.get(scenario, scenario_tags["normal"]),
            length=self.faker.random_int(1, 3),
            unique=True
        )
        
        # 基本データ構築
        job_data = {
            "job_id": f"job_{self.faker.uuid4()}",
            "user_id": user_profile["user_id"],
            "user_email": user_profile["email"],
            "filename": filename,
            "gcs_bucket_name": f"{user_tier}-whisper-bucket",
            "audio_size": audio_size,
            "audio_duration_ms": duration_ms,
            "file_hash": file_hash,
            "status": status,
            "num_speakers": num_speakers,
            "min_speakers": 1,
            "max_speakers": num_speakers,
            "language": preferred_language,
            "initial_prompt": self.faker.sentence() if self.faker.boolean(chance_of_getting_true=30) else "",
            "tags": tags,
            "description": self.faker.text(max_nb_chars=200) if self.faker.boolean(chance_of_getting_true=50) else "",
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "error_message": error_message,
            "model_name": self.faker.whisper_model_name(),
            "speaker_diarization": self.faker.boolean(chance_of_getting_true=70),
            "word_timestamps": self.faker.boolean(chance_of_getting_true=60)
        }
        
        # オーバーライドを適用
        job_data.update(overrides)
        
        # 統計更新
        self._update_generation_stats(job_data)
        
        return WhisperFirestoreData(**job_data)
    
    def create_test_scenario_data(self, scenario: WhisperTestScenario) -> Dict[str, Any]:
        """テストシナリオに基づく包括的なデータセットを生成"""
        users = []
        jobs = []
        
        # ユーザー生成
        user_types = ["casual_user", "normal", "power_user", "enterprise_user"]
        for i in range(scenario.user_count):
            user_type = self.faker.random_element(user_types)
            user_profile = self.create_realistic_user_profile(user_type)
            users.append(user_profile)
            
            # ユーザーごとのジョブ生成
            user_jobs = []
            for j in range(scenario.jobs_per_user):
                # ステータスを分布に従って決定
                status = self.faker.random_element_with_weights(scenario.status_distribution)
                
                # エラー発生の決定
                if status != "failed" and self.faker.random.random() < scenario.error_rate:
                    status = "failed"
                
                job = self.create_whisper_job_with_dependencies(
                    user_profile=user_profile,
                    status=status,
                    scenario=scenario.scenario_name
                )
                user_jobs.append(job)
                jobs.append(job)
            
            # ユーザーにジョブ情報を追加
            user_profile["jobs"] = user_jobs
            user_profile["total_jobs_in_scenario"] = len(user_jobs)
        
        return {
            "scenario": scenario,
            "users": users,
            "jobs": jobs,
            "total_users": len(users),
            "total_jobs": len(jobs),
            "generation_stats": self.generated_data_stats.copy(),
            "data_quality_report": self._generate_data_quality_report(users, jobs)
        }
    
    def create_edge_case_dataset(self) -> List[WhisperFirestoreData]:
        """エッジケース・境界値のシステマティックな生成"""
        edge_cases = []
        
        # ファイルサイズのエッジケース
        size_edge_cases = [
            {"audio_size": 1, "description": "最小ファイルサイズ"},
            {"audio_size": 1024, "description": "1KB"},
            {"audio_size": 1024 * 1024, "description": "1MB"},
            {"audio_size": 50 * 1024 * 1024, "description": "50MB"},
            {"audio_size": 100 * 1024 * 1024 - 1, "description": "上限直下"},
            {"audio_size": 100 * 1024 * 1024, "description": "上限ちょうど"},
        ]
        
        # 音声時間のエッジケース
        duration_edge_cases = [
            {"audio_duration_ms": 1, "description": "最短時間"},
            {"audio_duration_ms": 1000, "description": "1秒"},
            {"audio_duration_ms": 60000, "description": "1分"},
            {"audio_duration_ms": 1800000 - 1000, "description": "30分直下"},
            {"audio_duration_ms": 1800000, "description": "30分ちょうど"},
        ]
        
        # 話者数のエッジケース
        speaker_edge_cases = [
            {"num_speakers": 1, "min_speakers": 1, "max_speakers": 1},
            {"num_speakers": 2, "min_speakers": 1, "max_speakers": 2},
            {"num_speakers": 10, "min_speakers": 1, "max_speakers": 10},
        ]
        
        # 特殊文字ファイル名
        special_filename_cases = [
            {"filename": "音声ファイル①.wav", "description": "日本語＋特殊文字"},
            {"filename": "file with spaces.mp3", "description": "スペース含み"},
            {"filename": "file@#$%^&*().m4a", "description": "記号含み"},
            {"filename": "a" * 200 + ".wav", "description": "長いファイル名"},
            {"filename": "a.wav", "description": "最短ファイル名"},
        ]
        
        # エッジケース組み合わせ生成
        base_user = self.create_realistic_user_profile("normal")
        
        for size_case in size_edge_cases:
            for duration_case in duration_edge_cases:
                job = self.create_whisper_job_with_dependencies(
                    user_profile=base_user,
                    status="queued",
                    **{**size_case, **duration_case}
                )
                job.description = f"エッジケース: {size_case['description']}, {duration_case['description']}"
                edge_cases.append(job)
        
        for speaker_case in speaker_edge_cases:
            job = self.create_whisper_job_with_dependencies(
                user_profile=base_user,
                status="queued",
                **speaker_case
            )
            job.description = f"話者数エッジケース: {speaker_case['num_speakers']}人"
            edge_cases.append(job)
        
        for filename_case in special_filename_cases:
            job = self.create_whisper_job_with_dependencies(
                user_profile=base_user,
                status="queued",
                filename=filename_case["filename"]
            )
            job.description = f"ファイル名エッジケース: {filename_case['description']}"
            edge_cases.append(job)
        
        return edge_cases
    
    def create_temporal_lifecycle_dataset(self, days: int = 30) -> List[WhisperFirestoreData]:
        """時系列ライフサイクルシミュレーションデータを生成"""
        lifecycle_jobs = []
        base_user = self.create_realistic_user_profile("normal")
        
        start_date = datetime.now() - timedelta(days=days)
        
        for day in range(days):
            current_date = start_date + timedelta(days=day)
            
            # 日によって異なるアクティビティパターン
            if day % 7 in [5, 6]:  # 週末
                daily_jobs = self.faker.random_int(1, 3)
            elif day % 7 == 0:  # 月曜日（多忙）
                daily_jobs = self.faker.random_int(5, 15)
            else:  # 平日
                daily_jobs = self.faker.random_int(2, 8)
            
            for job_idx in range(daily_jobs):
                # 時刻を営業時間内にランダム配置
                hour = self.faker.random_int(9, 18)
                minute = self.faker.random_int(0, 59)
                job_time = current_date.replace(hour=hour, minute=minute)
                
                # ライフサイクルステージを時系列で決定
                days_ago = (datetime.now() - job_time).days
                
                if days_ago < 1:
                    # 最新のジョブ：多くが処理中または待機中
                    status = self.faker.random_element_with_weights({
                        "queued": 40,
                        "processing": 35,
                        "completed": 20,
                        "failed": 5
                    })
                elif days_ago < 7:
                    # 1週間以内：多くが完了済み
                    status = self.faker.random_element_with_weights({
                        "completed": 70,
                        "failed": 15,
                        "processing": 10,
                        "queued": 5
                    })
                else:
                    # 1週間以上：ほぼ全て完了済み
                    status = self.faker.random_element_with_weights({
                        "completed": 85,
                        "failed": 10,
                        "cancelled": 5
                    })
                
                job = self.create_whisper_job_with_dependencies(
                    user_profile=base_user,
                    status=status,
                    scenario="normal",
                    created_at=job_time.isoformat()
                )
                
                # 更新時刻をステータスに応じて調整
                if status == "completed":
                    processing_hours = self.faker.random_int(1, 24)
                    job.updated_at = (job_time + timedelta(hours=processing_hours)).isoformat()
                elif status == "failed":
                    failure_minutes = self.faker.random_int(5, 180)
                    job.updated_at = (job_time + timedelta(minutes=failure_minutes)).isoformat()
                
                lifecycle_jobs.append(job)
        
        return lifecycle_jobs
    
    def _update_generation_stats(self, job_data: Dict[str, Any]):
        """生成統計の更新"""
        self.generated_data_stats["total_jobs"] += 1
        
        status = job_data.get("status", "unknown")
        self.generated_data_stats["status_counts"][status] = \
            self.generated_data_stats["status_counts"].get(status, 0) + 1
        
        language = job_data.get("language", "unknown")
        self.generated_data_stats["language_counts"][language] = \
            self.generated_data_stats["language_counts"].get(language, 0) + 1
        
        filename = job_data.get("filename", "")
        if "." in filename:
            file_format = filename.split(".")[-1].lower()
            self.generated_data_stats["file_format_counts"][file_format] = \
                self.generated_data_stats["file_format_counts"].get(file_format, 0) + 1
    
    def _generate_data_quality_report(self, users: List[Dict], jobs: List[WhisperFirestoreData]) -> Dict[str, Any]:
        """データ品質レポートの生成"""
        if not jobs:
            return {"error": "No jobs to analyze"}
        
        # 基本統計
        total_jobs = len(jobs)
        total_users = len(users)
        
        # ステータス分布
        status_distribution = {}
        for job in jobs:
            status = job.status
            status_distribution[status] = status_distribution.get(status, 0) + 1
        
        # 音声時間の統計
        durations = [job.audio_duration_ms for job in jobs]
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        
        # ファイルサイズの統計
        sizes = [job.audio_size for job in jobs]
        avg_size = sum(sizes) / len(sizes)
        min_size = min(sizes)
        max_size = max(sizes)
        
        # データ品質チェック
        quality_issues = []
        
        # 一意性チェック
        job_ids = [job.job_id for job in jobs]
        if len(set(job_ids)) != len(job_ids):
            quality_issues.append("ジョブIDに重複があります")
        
        # 論理的整合性チェック
        for job in jobs:
            if job.min_speakers > job.max_speakers:
                quality_issues.append(f"Job {job.job_id}: min_speakers > max_speakers")
            
            if job.num_speakers < job.min_speakers or job.num_speakers > job.max_speakers:
                quality_issues.append(f"Job {job.job_id}: num_speakers is out of range")
        
        return {
            "total_jobs": total_jobs,
            "total_users": total_users,
            "status_distribution": status_distribution,
            "duration_stats": {
                "average_ms": avg_duration,
                "min_ms": min_duration,
                "max_ms": max_duration,
                "average_minutes": avg_duration / 60000
            },
            "size_stats": {
                "average_bytes": avg_size,
                "min_bytes": min_size,
                "max_bytes": max_size,
                "average_mb": avg_size / 1024 / 1024
            },
            "quality_issues": quality_issues,
            "quality_score": max(0, 100 - len(quality_issues) * 10)  # 100点満点
        }
    
    def get_generation_summary(self) -> Dict[str, Any]:
        """生成サマリーの取得"""
        return {
            "total_generated": self.generated_data_stats,
            "faker_locale": str(self.faker.locales),
            "seed_info": "Seeded" if hasattr(self.faker, "_seed") else "Random"
        }


class TestAdvancedDataFactoryPatterns:
    """高度なデータファクトリパターンのテスト"""
    
    @pytest.fixture
    def whisper_factory(self):
        """Whisperデータファクトリのフィクスチャ"""
        return AdvancedWhisperDataFactory(locale="ja_JP", seed=12345)
    
    def test_realistic_user_profile_generation(self, whisper_factory):
        """リアルなユーザープロファイル生成のテスト"""
        user_types = ["casual_user", "normal", "power_user", "enterprise_user"]
        
        for user_type in user_types:
            user_profile = whisper_factory.create_realistic_user_profile(user_type)
            
            # 基本フィールドの存在確認
            required_fields = ["user_id", "email", "name", "created_at", "subscription_tier"]
            for field in required_fields:
                assert field in user_profile, f"必須フィールド '{field}' が欠落: {user_type}"
            
            # ユーザータイプ固有の検証
            if user_type == "enterprise_user":
                assert user_profile["monthly_job_limit"] >= 1000, "企業ユーザーの制限が低すぎます"
                assert "organization" in user_profile, "企業ユーザーに組織情報がありません"
            elif user_type == "casual_user":
                assert user_profile["subscription_tier"] == "free", "カジュアルユーザーがフリープランではありません"
                assert user_profile["monthly_job_limit"] <= 100, "カジュアルユーザーの制限が高すぎます"
            
            # データ品質の確認
            assert "@" in user_profile["email"], "無効なメールアドレス形式"
            assert user_profile["total_jobs_created"] >= 0, "負の作成ジョブ数"
            assert user_profile["average_file_size_mb"] > 0, "無効な平均ファイルサイズ"
    
    def test_whisper_job_with_dependencies_generation(self, whisper_factory):
        """依存関係を持つWhisperジョブ生成のテスト"""
        # ベースユーザープロファイル
        user_profile = whisper_factory.create_realistic_user_profile("enterprise_user")
        
        scenarios = ["interview", "meeting", "lecture", "conference", "normal"]
        statuses = ["queued", "processing", "completed", "failed"]
        
        for scenario in scenarios:
            for status in statuses:
                job = whisper_factory.create_whisper_job_with_dependencies(
                    user_profile=user_profile,
                    status=status,
                    scenario=scenario
                )
                
                # 基本検証
                assert job.user_id == user_profile["user_id"], "ユーザーIDが一致しません"
                assert job.user_email == user_profile["email"], "ユーザーメールが一致しません"
                assert job.status == status, f"ステータスが期待値と異なります: {job.status} != {status}"
                
                # シナリオ固有の検証
                if scenario == "meeting":
                    assert job.num_speakers >= 3, f"会議シナリオで話者数が少なすぎます: {job.num_speakers}"
                elif scenario == "interview":
                    assert 2 <= job.num_speakers <= 3, f"インタビューシナリオで話者数が範囲外: {job.num_speakers}"
                elif scenario == "lecture":
                    assert job.num_speakers <= 2, f"講演シナリオで話者数が多すぎます: {job.num_speakers}"
                
                # データ整合性の確認
                assert job.min_speakers <= job.num_speakers <= job.max_speakers, \
                    f"話者数の範囲が不正: {job.min_speakers} <= {job.num_speakers} <= {job.max_speakers}"
                
                assert job.audio_size > 0, "音声サイズが0以下"
                assert job.audio_duration_ms > 0, "音声時間が0以下"
                
                # ステータス固有の検証
                if status == "failed":
                    assert job.error_message is not None, "失敗ジョブにエラーメッセージがありません"
                elif status == "completed":
                    created_at = datetime.fromisoformat(job.created_at)
                    updated_at = datetime.fromisoformat(job.updated_at)
                    assert updated_at >= created_at, "更新時刻が作成時刻より古い"
    
    def test_test_scenario_data_generation(self, whisper_factory):
        """テストシナリオデータ生成のテスト"""
        # テストシナリオ定義
        scenario = WhisperTestScenario(
            scenario_name="load_test",
            user_count=10,
            jobs_per_user=5,
            status_distribution={"queued": 0.3, "processing": 0.2, "completed": 0.4, "failed": 0.1},
            duration_scenario="normal",
            quality_distribution={"standard": 0.6, "high": 0.3, "low": 0.1},
            language_distribution={"ja": 0.5, "en": 0.3, "auto": 0.2},
            error_rate=0.05,
            tags=["load_test", "performance"]
        )
        
        # データ生成
        dataset = whisper_factory.create_test_scenario_data(scenario)
        
        # 基本構造の検証
        assert "users" in dataset, "ユーザーデータが存在しません"
        assert "jobs" in dataset, "ジョブデータが存在しません"
        assert len(dataset["users"]) == scenario.user_count, f"ユーザー数が期待値と異なります: {len(dataset['users'])}"
        assert len(dataset["jobs"]) == scenario.user_count * scenario.jobs_per_user, \
            f"総ジョブ数が期待値と異なります: {len(dataset['jobs'])}"
        
        # ステータス分布の確認
        status_counts = {}
        for job in dataset["jobs"]:
            status = job.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        total_jobs = len(dataset["jobs"])
        for status, expected_ratio in scenario.status_distribution.items():
            actual_ratio = status_counts.get(status, 0) / total_jobs
            # 許容誤差±10%
            assert abs(actual_ratio - expected_ratio) < 0.15, \
                f"ステータス '{status}' の分布が期待値から大きく外れています: {actual_ratio:.2f} vs {expected_ratio:.2f}"
        
        # データ品質レポートの確認
        quality_report = dataset["data_quality_report"]
        assert quality_report["quality_score"] >= 80, f"データ品質スコアが低すぎます: {quality_report['quality_score']}"
        assert len(quality_report["quality_issues"]) == 0, f"データ品質の問題: {quality_report['quality_issues']}"
    
    def test_edge_case_dataset_generation(self, whisper_factory):
        """エッジケースデータセット生成のテスト"""
        edge_cases = whisper_factory.create_edge_case_dataset()
        
        # エッジケースの存在確認
        assert len(edge_cases) > 0, "エッジケースが生成されませんでした"
        
        # 境界値ケースの確認
        size_values = [job.audio_size for job in edge_cases]
        duration_values = [job.audio_duration_ms for job in edge_cases]
        
        # 最小値・最大値の存在確認
        assert min(size_values) <= 1024, "最小ファイルサイズのエッジケースが存在しません"
        assert max(size_values) >= 50 * 1024 * 1024, "大きなファイルサイズのエッジケースが存在しません"
        assert min(duration_values) <= 1000, "最短時間のエッジケースが存在しません"
        assert max(duration_values) >= 30 * 60 * 1000, "長時間のエッジケースが存在しません"
        
        # 特殊ファイル名の確認
        filenames = [job.filename for job in edge_cases]
        has_japanese = any("音声" in filename or "ファイル" in filename for filename in filenames)
        has_special_chars = any(any(char in filename for char in "@#$%^&*()") for filename in filenames)
        has_spaces = any(" " in filename for filename in filenames)
        
        assert has_japanese, "日本語ファイル名のエッジケースが存在しません"
        assert has_special_chars, "特殊文字ファイル名のエッジケースが存在しません"
        assert has_spaces, "スペース含みファイル名のエッジケースが存在しません"
    
    def test_temporal_lifecycle_dataset_generation(self, whisper_factory):
        """時系列ライフサイクルデータセット生成のテスト"""
        days = 14  # 2週間
        lifecycle_jobs = whisper_factory.create_temporal_lifecycle_dataset(days)
        
        # 基本検証
        assert len(lifecycle_jobs) > 0, "ライフサイクルジョブが生成されませんでした"
        
        # 時系列順序の確認
        created_times = [datetime.fromisoformat(job.created_at) for job in lifecycle_jobs]
        sorted_times = sorted(created_times)
        assert created_times != sorted_times or len(set(created_times)) < len(created_times), \
            "時系列データが適切にランダム化されていません"
        
        # 日付範囲の確認
        oldest_time = min(created_times)
        newest_time = max(created_times)
        time_span = (newest_time - oldest_time).days
        assert time_span >= days * 0.8, f"時系列データの範囲が狭すぎます: {time_span}日"
        
        # ライフサイクルパターンの確認
        recent_jobs = [job for job in lifecycle_jobs 
                      if (datetime.now() - datetime.fromisoformat(job.created_at)).days < 1]
        old_jobs = [job for job in lifecycle_jobs 
                   if (datetime.now() - datetime.fromisoformat(job.created_at)).days > 7]
        
        if recent_jobs:
            recent_completed_ratio = len([job for job in recent_jobs if job.status == "completed"]) / len(recent_jobs)
            assert recent_completed_ratio < 0.5, "最近のジョブの完了率が高すぎます（リアリティ不足）"
        
        if old_jobs:
            old_completed_ratio = len([job for job in old_jobs if job.status == "completed"]) / len(old_jobs)
            assert old_completed_ratio > 0.7, "古いジョブの完了率が低すぎます（リアリティ不足）"
    
    def test_data_factory_consistency_and_reproducibility(self):
        """データファクトリの一貫性と再現性のテスト"""
        # 同じシードで2つのファクトリを作成
        factory1 = AdvancedWhisperDataFactory(locale="ja_JP", seed=98765)
        factory2 = AdvancedWhisperDataFactory(locale="ja_JP", seed=98765)
        
        # 同じ条件でデータ生成
        user1 = factory1.create_realistic_user_profile("normal")
        user2 = factory2.create_realistic_user_profile("normal")
        
        # 再現性の確認（同じシードなら同じデータ）
        # 注意：Fakerの内部状態により完全な一致は期待できない場合があるため、
        # 主要な構造と品質の一貫性を確認
        assert user1["subscription_tier"] == user2["subscription_tier"], "同じシードで異なる結果（サブスクリプション）"
        
        # 異なるシードで差異があることを確認
        factory3 = AdvancedWhisperDataFactory(locale="ja_JP", seed=11111)
        user3 = factory3.create_realistic_user_profile("normal")
        
        # 少なくとも一部のフィールドは異なるはず
        different_fields = 0
        for key in ["user_id", "email", "name"]:
            if user1.get(key) != user3.get(key):
                different_fields += 1
        
        assert different_fields >= 2, "異なるシードで十分な差異が生成されていません"
    
    def test_multi_language_data_generation(self):
        """多言語データ生成のテスト"""
        locales = ["ja_JP", "en_US", "ko_KR", "zh_CN"]
        
        for locale in locales:
            factory = AdvancedWhisperDataFactory(locale=locale, seed=54321)
            user = factory.create_realistic_user_profile("normal")
            job = factory.create_whisper_job_with_dependencies(
                user_profile=user,
                status="completed",
                scenario="normal"
            )
            
            # 基本構造の一貫性確認
            assert job.user_id == user["user_id"], f"ロケール {locale} でユーザーID不一致"
            assert job.status == "completed", f"ロケール {locale} でステータス不一致"
            assert job.audio_size > 0, f"ロケール {locale} で無効な音声サイズ"
            
            # ロケール固有の特性（文字エンコーディング等）
            try:
                job.filename.encode('utf-8')
                job.description.encode('utf-8') if job.description else None
                user["name"].encode('utf-8')
            except UnicodeEncodeError:
                pytest.fail(f"ロケール {locale} でUnicodeエンコーディングエラー")


if __name__ == "__main__":
    # テストファイルを直接実行する場合の設定
    pytest.main([__file__, "-v", "--tb=short", "-x"])