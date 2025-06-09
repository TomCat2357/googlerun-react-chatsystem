"""
高度なパフォーマンス・負荷テスト：スケーラビリティと性能特性の検証
Advanced Performance and Load Testing for Scalability Verification

このテストファイルは、以下の高度なパフォーマンステスト戦略を実装します：
1. 同期・非同期負荷テスト
2. メモリ効率性とリソース使用量測定
3. スループット・レイテンシ分析
4. ストレステストとカオステスト
5. 時間固定テスト（freezegun）
6. リアルタイム性能監視
"""

import pytest
import asyncio
import time
import psutil
import threading
import queue
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable
from unittest.mock import patch, MagicMock, create_autospec
from contextlib import contextmanager
import statistics
import os
import tempfile
from faker import Faker
from freezegun import freeze_time
import numpy as np

# プロジェクト固有のインポート
from common_utils.class_types import WhisperFirestoreData


@dataclass
class PerformanceMetrics:
    """パフォーマンス測定結果"""
    operation_name: str
    total_operations: int
    success_count: int
    failure_count: int
    total_duration_seconds: float
    average_duration_seconds: float
    median_duration_seconds: float
    p95_duration_seconds: float
    p99_duration_seconds: float
    operations_per_second: float
    peak_memory_mb: float
    memory_increase_mb: float
    cpu_usage_percent: float
    error_rate_percent: float


class PerformanceTestHarness:
    """パフォーマンステスト用のハーネス"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.start_memory = None
        self.peak_memory = None
        self.start_time = None
        self.end_time = None
        self.operation_times = []
        self.errors = []
        self.cpu_samples = []
    
    @contextmanager
    def measure_performance(self, operation_name: str):
        """パフォーマンス測定のコンテキストマネージャー"""
        self.start_memory = self.process.memory_info().rss
        self.start_time = time.time()
        self.operation_times = []
        self.errors = []
        self.cpu_samples = []
        
        # CPU使用率サンプリング用スレッド
        cpu_monitor_active = threading.Event()
        cpu_monitor_active.set()
        
        def monitor_cpu():
            while cpu_monitor_active.is_set():
                self.cpu_samples.append(self.process.cpu_percent())
                time.sleep(0.1)
        
        cpu_thread = threading.Thread(target=monitor_cpu, daemon=True)
        cpu_thread.start()
        
        try:
            yield self
        finally:
            cpu_monitor_active.clear()
            cpu_thread.join(timeout=1.0)
            
            self.end_time = time.time()
            self.peak_memory = self.process.memory_info().rss
    
    def record_operation(self, duration: float, success: bool = True, error: Optional[str] = None):
        """操作結果の記録"""
        self.operation_times.append(duration)
        if not success and error:
            self.errors.append(error)
    
    def get_metrics(self, operation_name: str) -> PerformanceMetrics:
        """パフォーマンスメトリクスの計算"""
        if not self.operation_times:
            raise ValueError("No operations recorded")
        
        total_duration = self.end_time - self.start_time if self.end_time and self.start_time else 0
        success_count = len(self.operation_times) - len(self.errors)
        failure_count = len(self.errors)
        total_operations = len(self.operation_times)
        
        return PerformanceMetrics(
            operation_name=operation_name,
            total_operations=total_operations,
            success_count=success_count,
            failure_count=failure_count,
            total_duration_seconds=total_duration,
            average_duration_seconds=statistics.mean(self.operation_times),
            median_duration_seconds=statistics.median(self.operation_times),
            p95_duration_seconds=np.percentile(self.operation_times, 95),
            p99_duration_seconds=np.percentile(self.operation_times, 99),
            operations_per_second=total_operations / total_duration if total_duration > 0 else 0,
            peak_memory_mb=(self.peak_memory - self.start_memory) / 1024 / 1024 if self.peak_memory and self.start_memory else 0,
            memory_increase_mb=(self.peak_memory - self.start_memory) / 1024 / 1024 if self.peak_memory and self.start_memory else 0,
            cpu_usage_percent=statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
            error_rate_percent=(failure_count / total_operations * 100) if total_operations > 0 else 0
        )


class TestConcurrentLoadScenarios:
    """並行・負荷シナリオテスト"""
    
    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_whisper_job_creation_load(self, enhanced_gcp_services):
        """並行Whisperジョブ作成負荷テスト"""
        harness = PerformanceTestHarness()
        
        # テスト設定
        concurrent_jobs = 50
        max_workers = 10
        
        def create_single_job(job_index: int) -> Dict[str, Any]:
            """単一ジョブ作成処理"""
            start_time = time.time()
            try:
                job_data = {
                    "job_id": f"load_test_job_{job_index}_{uuid.uuid4().hex[:8]}",
                    "user_id": f"user_{job_index % 10}",  # 10ユーザーで分散
                    "filename": f"load_test_audio_{job_index}.wav",
                    "audio_size": 1024 * 1024 * (5 + job_index % 20),  # 5-25MB
                    "audio_duration_ms": 60000 + (job_index % 600) * 1000,  # 1-11分
                    "status": "queued"
                }
                
                # GCS操作シミュレーション
                bucket = enhanced_gcp_services["storage"].bucket("test-bucket")
                blob = bucket.blob(f"whisper/{job_data['job_id']}.wav")
                blob.upload_from_string(f"mock_audio_data_{job_index}", content_type="audio/wav")
                
                # Firestore操作シミュレーション
                collection = enhanced_gcp_services["firestore"].collection("whisper_jobs")
                collection.document(job_data["job_id"]).set(job_data)
                
                # Pub/Sub操作シミュレーション
                enhanced_gcp_services["pubsub"].publish(
                    topic="whisper-queue",
                    data=json.dumps({"job_id": job_data["job_id"]}).encode()
                )
                
                duration = time.time() - start_time
                return {"success": True, "duration": duration, "job_id": job_data["job_id"]}
                
            except Exception as e:
                duration = time.time() - start_time
                return {"success": False, "duration": duration, "error": str(e)}
        
        # 負荷テスト実行
        with harness.measure_performance("concurrent_job_creation"):
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 全ジョブを並行実行
                future_to_index = {
                    executor.submit(create_single_job, i): i 
                    for i in range(concurrent_jobs)
                }
                
                # 結果収集
                for future in as_completed(future_to_index):
                    result = future.result()
                    harness.record_operation(
                        duration=result["duration"],
                        success=result["success"],
                        error=result.get("error")
                    )
        
        # パフォーマンス評価
        metrics = harness.get_metrics("concurrent_job_creation")
        
        # アサーション
        assert metrics.success_count >= concurrent_jobs * 0.95, f"成功率が低すぎます: {metrics.success_count}/{concurrent_jobs}"
        assert metrics.operations_per_second > 5.0, f"スループットが低すぎます: {metrics.operations_per_second} ops/sec"
        assert metrics.p95_duration_seconds < 5.0, f"95%ile応答時間が遅すぎます: {metrics.p95_duration_seconds}秒"
        assert metrics.memory_increase_mb < 100, f"メモリ使用量が多すぎます: {metrics.memory_increase_mb}MB"
        assert metrics.error_rate_percent < 5.0, f"エラー率が高すぎます: {metrics.error_rate_percent}%"
        
        # 詳細レポート出力
        print(f"\n=== 並行負荷テスト結果 ===")
        print(f"総操作数: {metrics.total_operations}")
        print(f"成功数: {metrics.success_count}")
        print(f"失敗数: {metrics.failure_count}")
        print(f"スループット: {metrics.operations_per_second:.2f} ops/sec")
        print(f"平均応答時間: {metrics.average_duration_seconds:.3f}秒")
        print(f"95%ile応答時間: {metrics.p95_duration_seconds:.3f}秒")
        print(f"メモリ増加量: {metrics.memory_increase_mb:.2f}MB")
        print(f"CPU使用率: {metrics.cpu_usage_percent:.1f}%")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_async_websocket_connection_load(self):
        """非同期WebSocket接続負荷テスト"""
        harness = PerformanceTestHarness()
        
        # WebSocket接続のモック
        class MockWebSocket:
            def __init__(self, connection_id: str):
                self.connection_id = connection_id
                self.connected = False
                self.messages_sent = 0
                self.messages_received = 0
            
            async def connect(self):
                """接続シミュレーション"""
                await asyncio.sleep(0.01)  # ネットワーク遅延シミュレート
                self.connected = True
            
            async def send_message(self, message: str):
                """メッセージ送信シミュレーション"""
                if not self.connected:
                    raise RuntimeError("Not connected")
                await asyncio.sleep(0.005)  # 送信遅延
                self.messages_sent += 1
            
            async def receive_message(self) -> str:
                """メッセージ受信シミュレーション"""
                if not self.connected:
                    raise RuntimeError("Not connected")
                await asyncio.sleep(0.003)  # 受信遅延
                self.messages_received += 1
                return f"response_{self.messages_received}"
            
            async def disconnect(self):
                """切断シミュレーション"""
                self.connected = False
        
        async def websocket_session(session_id: int) -> Dict[str, Any]:
            """WebSocketセッションシミュレーション"""
            start_time = time.time()
            try:
                ws = MockWebSocket(f"session_{session_id}")
                
                # 接続
                await ws.connect()
                
                # メッセージ交換（10回）
                for i in range(10):
                    await ws.send_message(f"message_{i}")
                    response = await ws.receive_message()
                    assert response.startswith("response_")
                
                # 切断
                await ws.disconnect()
                
                duration = time.time() - start_time
                return {
                    "success": True,
                    "duration": duration,
                    "messages_sent": ws.messages_sent,
                    "messages_received": ws.messages_received
                }
                
            except Exception as e:
                duration = time.time() - start_time
                return {"success": False, "duration": duration, "error": str(e)}
        
        # 非同期負荷テスト実行
        concurrent_sessions = 100
        
        with harness.measure_performance("async_websocket_load"):
            # 全セッションを並行実行
            tasks = [websocket_session(i) for i in range(concurrent_sessions)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 結果処理
            for result in results:
                if isinstance(result, Exception):
                    harness.record_operation(0, success=False, error=str(result))
                else:
                    harness.record_operation(
                        duration=result["duration"],
                        success=result["success"],
                        error=result.get("error")
                    )
        
        # パフォーマンス評価
        metrics = harness.get_metrics("async_websocket_load")
        
        # アサーション
        assert metrics.success_count >= concurrent_sessions * 0.98, f"WebSocket接続成功率が低い: {metrics.success_count}/{concurrent_sessions}"
        assert metrics.operations_per_second > 20.0, f"WebSocketスループットが低い: {metrics.operations_per_second} sessions/sec"
        assert metrics.p95_duration_seconds < 2.0, f"WebSocket応答時間が遅い: {metrics.p95_duration_seconds}秒"


class TestMemoryEfficiencyPatterns:
    """メモリ効率性テストパターン"""
    
    @pytest.mark.performance
    def test_large_audio_file_streaming_memory_efficiency(self):
        """大きな音声ファイルのストリーミング処理メモリ効率性テスト"""
        harness = PerformanceTestHarness()
        
        # 大きなファイルサイズをシミュレート（100MB）
        large_file_size = 100 * 1024 * 1024
        chunk_size = 1024 * 1024  # 1MBチャンク
        
        def stream_process_audio(file_size: int, chunk_size: int) -> Dict[str, Any]:
            """ストリーミング音声処理シミュレーション"""
            processed_bytes = 0
            chunks_processed = 0
            
            # チャンクごとの処理
            for offset in range(0, file_size, chunk_size):
                current_chunk_size = min(chunk_size, file_size - offset)
                
                # チャンクデータのシミュレーション（実際にはメモリは使わない）
                chunk_data = f"chunk_{offset}_{current_chunk_size}"
                
                # 音声処理シミュレーション
                processed_chunk = self._process_audio_chunk(chunk_data)
                
                processed_bytes += current_chunk_size
                chunks_processed += 1
                
                # ガベージコレクション的処理（メモリ解放）
                del chunk_data, processed_chunk
            
            return {
                "processed_bytes": processed_bytes,
                "chunks_processed": chunks_processed,
                "average_chunk_size": processed_bytes / chunks_processed
            }
        
        # メモリ効率性テスト実行
        with harness.measure_performance("large_file_streaming"):
            result = stream_process_audio(large_file_size, chunk_size)
            harness.record_operation(
                duration=0.1,  # シミュレーション時間
                success=True
            )
        
        metrics = harness.get_metrics("large_file_streaming")
        
        # メモリ効率性の検証
        assert metrics.memory_increase_mb < 50, f"メモリ使用量が非効率的: {metrics.memory_increase_mb}MB"
        assert result["processed_bytes"] == large_file_size, "全データが処理されていません"
        assert result["chunks_processed"] == large_file_size // chunk_size, "チャンク数が期待値と異なります"
        
        print(f"\n=== メモリ効率性テスト結果 ===")
        print(f"処理データサイズ: {result['processed_bytes'] / 1024 / 1024:.1f}MB")
        print(f"チャンク数: {result['chunks_processed']}")
        print(f"メモリ増加量: {metrics.memory_increase_mb:.2f}MB")
        print(f"メモリ効率性: {result['processed_bytes'] / 1024 / 1024 / metrics.memory_increase_mb:.1f}x")
    
    def _process_audio_chunk(self, chunk_data: str) -> str:
        """音声チャンク処理のシミュレーション"""
        # 実際の音声処理をシミュレート
        return f"processed_{chunk_data}"
    
    @pytest.mark.performance
    def test_memory_leak_detection_in_batch_processing(self):
        """バッチ処理でのメモリリーク検出テスト"""
        harness = PerformanceTestHarness()
        
        def create_and_process_jobs(batch_size: int) -> List[Dict[str, Any]]:
            """ジョブ作成・処理のバッチ実行"""
            jobs = []
            
            for i in range(batch_size):
                # ジョブデータ作成
                job_data = WhisperFirestoreData(
                    job_id=f"batch_job_{i}",
                    user_id=f"user_{i}",
                    user_email=f"user_{i}@example.com",
                    filename=f"batch_audio_{i}.wav",
                    gcs_bucket_name="test-bucket",
                    audio_size=1024 * 1024,  # 1MB
                    audio_duration_ms=60000,  # 1分
                    file_hash=f"hash_{i}",
                    status="queued"
                )
                
                # 処理シミュレーション
                processed_job = self._simulate_job_processing(job_data)
                jobs.append(processed_job.dict())
                
                # 明示的にオブジェクトを削除（メモリリーク防止）
                del job_data, processed_job
            
            return jobs
        
        # 複数バッチでメモリ使用量を監視
        batch_sizes = [10, 20, 50, 100]
        memory_measurements = []
        
        for batch_size in batch_sizes:
            with harness.measure_performance(f"batch_processing_{batch_size}"):
                jobs = create_and_process_jobs(batch_size)
                harness.record_operation(duration=0.1, success=True)
            
            metrics = harness.get_metrics(f"batch_processing_{batch_size}")
            memory_measurements.append({
                "batch_size": batch_size,
                "memory_increase_mb": metrics.memory_increase_mb,
                "memory_per_job_kb": metrics.memory_increase_mb * 1024 / batch_size
            })
            
            # バッチ間でのガベージコレクション
            import gc
            gc.collect()
        
        # メモリリーク検出
        memory_per_job_values = [m["memory_per_job_kb"] for m in memory_measurements]
        memory_variance = statistics.variance(memory_per_job_values) if len(memory_per_job_values) > 1 else 0
        
        # アサーション
        assert memory_variance < 100, f"ジョブあたりメモリ使用量の分散が大きい（メモリリークの疑い）: {memory_variance:.2f}"
        
        for measurement in memory_measurements:
            assert measurement["memory_per_job_kb"] < 50, f"ジョブあたりメモリ使用量が多い: {measurement['memory_per_job_kb']:.2f}KB"
        
        print(f"\n=== メモリリーク検出テスト結果 ===")
        for m in memory_measurements:
            print(f"バッチサイズ {m['batch_size']}: {m['memory_per_job_kb']:.2f}KB/job")
        print(f"メモリ使用量分散: {memory_variance:.2f}")
    
    def _simulate_job_processing(self, job_data: WhisperFirestoreData) -> WhisperFirestoreData:
        """ジョブ処理シミュレーション"""
        # 処理済みジョブデータを返す
        job_data.status = "completed"
        return job_data


class TestTemporalPerformancePatterns:
    """時間軸パフォーマンステスト"""
    
    @freeze_time("2024-01-01 12:00:00")
    @pytest.mark.performance
    def test_time_sensitive_operations_performance(self):
        """時間固定環境での時間敏感操作のパフォーマンステスト"""
        harness = PerformanceTestHarness()
        
        def time_sensitive_operation(operation_id: int) -> Dict[str, Any]:
            """時間敏感操作のシミュレーション"""
            start_time = time.time()
            
            # タイムスタンプベースの処理
            current_timestamp = int(time.time())
            operation_data = {
                "operation_id": operation_id,
                "timestamp": current_timestamp,
                "expires_at": current_timestamp + 3600,  # 1時間後に期限切れ
                "created_at": current_timestamp
            }
            
            # 時間ベースの検証
            if operation_data["expires_at"] <= operation_data["created_at"]:
                raise ValueError("Invalid expiration time")
            
            # 時間計算集約的な処理のシミュレーション
            time_calculations = []
            for i in range(1000):
                calc_result = operation_data["timestamp"] + i * 60
                time_calculations.append(calc_result)
            
            duration = time.time() - start_time
            return {
                "success": True,
                "duration": duration,
                "calculations_count": len(time_calculations),
                "final_timestamp": operation_data["expires_at"]
            }
        
        # 時間固定環境でのパフォーマンステスト
        operations_count = 100
        
        with harness.measure_performance("time_sensitive_operations"):
            for i in range(operations_count):
                result = time_sensitive_operation(i)
                harness.record_operation(
                    duration=result["duration"],
                    success=result["success"]
                )
        
        metrics = harness.get_metrics("time_sensitive_operations")
        
        # 時間固定環境での一貫性確認
        assert metrics.success_count == operations_count, "一部操作が失敗しました"
        assert metrics.average_duration_seconds < 0.01, f"時間計算が遅すぎます: {metrics.average_duration_seconds:.4f}秒"
        
        print(f"\n=== 時間敏感操作パフォーマンステスト結果 ===")
        print(f"全操作成功: {metrics.success_count}/{operations_count}")
        print(f"平均実行時間: {metrics.average_duration_seconds:.4f}秒")
        print(f"時間計算処理速度: {operations_count / metrics.total_duration_seconds:.1f} ops/sec")


class TestStressAndChaosPatterns:
    """ストレステストとカオステスト"""
    
    @pytest.mark.stress
    @pytest.mark.slow
    def test_extreme_load_stress_test(self, enhanced_gcp_services):
        """極限負荷ストレステスト"""
        harness = PerformanceTestHarness()
        
        # 極限設定
        extreme_concurrent_jobs = 200
        extreme_max_workers = 20
        
        def extreme_load_operation(operation_id: int) -> Dict[str, Any]:
            """極限負荷操作"""
            start_time = time.time()
            try:
                # CPU集約的処理のシミュレーション
                cpu_intensive_result = sum(i * i for i in range(10000))
                
                # メモリ集約的処理のシミュレーション
                memory_intensive_data = [f"data_{i}_{operation_id}" for i in range(1000)]
                
                # I/O集約的処理のシミュレーション
                with tempfile.NamedTemporaryFile(mode='w', delete=True) as tmp_file:
                    json.dump(memory_intensive_data, tmp_file)
                    tmp_file.flush()
                
                duration = time.time() - start_time
                return {
                    "success": True,
                    "duration": duration,
                    "cpu_result": cpu_intensive_result,
                    "memory_objects": len(memory_intensive_data)
                }
                
            except Exception as e:
                duration = time.time() - start_time
                return {"success": False, "duration": duration, "error": str(e)}
        
        # 極限負荷テスト実行
        with harness.measure_performance("extreme_load_stress"):
            with ThreadPoolExecutor(max_workers=extreme_max_workers) as executor:
                future_to_id = {
                    executor.submit(extreme_load_operation, i): i 
                    for i in range(extreme_concurrent_jobs)
                }
                
                for future in as_completed(future_to_id):
                    result = future.result()
                    harness.record_operation(
                        duration=result["duration"],
                        success=result["success"],
                        error=result.get("error")
                    )
        
        metrics = harness.get_metrics("extreme_load_stress")
        
        # ストレステスト許容基準（通常より緩和）
        min_success_rate = 0.80  # 80%以上の成功率
        max_error_rate = 20.0    # 20%以下のエラー率
        
        assert metrics.success_count >= extreme_concurrent_jobs * min_success_rate, (
            f"ストレステスト成功率が低い: {metrics.success_count}/{extreme_concurrent_jobs} "
            f"({metrics.success_count/extreme_concurrent_jobs*100:.1f}%)"
        )
        assert metrics.error_rate_percent <= max_error_rate, f"エラー率が高すぎます: {metrics.error_rate_percent:.1f}%"
        
        print(f"\n=== 極限負荷ストレステスト結果 ===")
        print(f"並行処理数: {extreme_concurrent_jobs}")
        print(f"ワーカー数: {extreme_max_workers}")
        print(f"成功率: {metrics.success_count/extreme_concurrent_jobs*100:.1f}%")
        print(f"エラー率: {metrics.error_rate_percent:.1f}%")
        print(f"スループット: {metrics.operations_per_second:.2f} ops/sec")
        print(f"メモリ使用量: {metrics.memory_increase_mb:.2f}MB")
    
    @pytest.mark.chaos
    def test_chaos_engineering_failure_injection(self, enhanced_gcp_services, advanced_mock_behaviors):
        """カオスエンジニアリング：障害注入テスト"""
        harness = PerformanceTestHarness()
        
        # 障害シナリオの定義
        failure_scenarios = [
            {"type": "network_timeout", "probability": 0.1},
            {"type": "memory_error", "probability": 0.05},
            {"type": "disk_full", "probability": 0.02},
            {"type": "permission_denied", "probability": 0.03},
            {"type": "rate_limit", "probability": 0.08}
        ]
        
        def chaos_operation(operation_id: int) -> Dict[str, Any]:
            """カオス的障害注入操作"""
            start_time = time.time()
            
            # ランダム障害注入
            import random
            for scenario in failure_scenarios:
                if random.random() < scenario["probability"]:
                    # 障害をシミュレート
                    error_type = scenario["type"]
                    duration = time.time() - start_time
                    return {
                        "success": False,
                        "duration": duration,
                        "error": f"Chaos engineering failure: {error_type}",
                        "injected_failure": error_type
                    }
            
            # 正常処理
            try:
                # 通常の処理をシミュレート
                result_data = self._simulate_normal_processing(operation_id)
                duration = time.time() - start_time
                return {
                    "success": True,
                    "duration": duration,
                    "result": result_data
                }
                
            except Exception as e:
                duration = time.time() - start_time
                return {
                    "success": False,
                    "duration": duration,
                    "error": f"Unexpected error: {str(e)}"
                }
        
        # カオステスト実行
        chaos_operations_count = 100
        injected_failures = []
        
        with harness.measure_performance("chaos_engineering"):
            for i in range(chaos_operations_count):
                result = chaos_operation(i)
                harness.record_operation(
                    duration=result["duration"],
                    success=result["success"],
                    error=result.get("error")
                )
                
                if not result["success"] and "injected_failure" in result:
                    injected_failures.append(result["injected_failure"])
        
        metrics = harness.get_metrics("chaos_engineering")
        
        # カオステスト評価
        expected_failure_rate = sum(s["probability"] for s in failure_scenarios) * 100
        actual_failure_rate = metrics.error_rate_percent
        
        # システムの回復力確認
        assert metrics.success_count > 0, "全操作が失敗しました（システムが完全に停止）"
        assert actual_failure_rate <= expected_failure_rate * 1.5, (
            f"実際の障害率が期待値を大幅に超過: {actual_failure_rate:.1f}% > {expected_failure_rate * 1.5:.1f}%"
        )
        
        # 障害パターンの多様性確認
        unique_failure_types = set(injected_failures)
        assert len(unique_failure_types) >= 2, "障害パターンの多様性が不足しています"
        
        print(f"\n=== カオスエンジニアリングテスト結果 ===")
        print(f"総操作数: {chaos_operations_count}")
        print(f"期待障害率: {expected_failure_rate:.1f}%")
        print(f"実際障害率: {actual_failure_rate:.1f}%")
        print(f"注入された障害タイプ: {list(unique_failure_types)}")
        print(f"システム回復力: {metrics.success_count/chaos_operations_count*100:.1f}%")
    
    def _simulate_normal_processing(self, operation_id: int) -> Dict[str, Any]:
        """通常処理のシミュレーション"""
        return {
            "operation_id": operation_id,
            "processed_at": time.time(),
            "result_size": 1024 * (operation_id % 10 + 1)
        }


class TestRealTimePerformanceMonitoring:
    """リアルタイム性能監視テスト"""
    
    @pytest.mark.performance
    def test_real_time_performance_monitoring_dashboard(self):
        """リアルタイム性能監視ダッシュボードテスト"""
        
        class PerformanceMonitor:
            def __init__(self):
                self.metrics_history = []
                self.alert_threshold = {
                    "response_time_ms": 1000,
                    "error_rate_percent": 5.0,
                    "memory_usage_mb": 100,
                    "cpu_usage_percent": 80.0
                }
                self.alerts = []
            
            def record_metric(self, metric_data: Dict[str, Any]):
                """メトリクス記録"""
                self.metrics_history.append(metric_data)
                self._check_alerts(metric_data)
            
            def _check_alerts(self, metric_data: Dict[str, Any]):
                """アラート監視"""
                for key, threshold in self.alert_threshold.items():
                    if metric_data.get(key, 0) > threshold:
                        self.alerts.append({
                            "timestamp": time.time(),
                            "metric": key,
                            "value": metric_data[key],
                            "threshold": threshold
                        })
            
            def get_current_health_status(self) -> Dict[str, Any]:
                """現在の健全性ステータス"""
                if not self.metrics_history:
                    return {"status": "unknown", "alerts": []}
                
                recent_metrics = self.metrics_history[-10:]  # 直近10件
                avg_response_time = statistics.mean(m.get("response_time_ms", 0) for m in recent_metrics)
                avg_error_rate = statistics.mean(m.get("error_rate_percent", 0) for m in recent_metrics)
                
                status = "healthy"
                if len(self.alerts) > 0:
                    status = "warning" if len(self.alerts) < 5 else "critical"
                
                return {
                    "status": status,
                    "avg_response_time_ms": avg_response_time,
                    "avg_error_rate_percent": avg_error_rate,
                    "total_alerts": len(self.alerts),
                    "recent_alerts": self.alerts[-3:] if self.alerts else []
                }
        
        # 性能監視テスト実行
        monitor = PerformanceMonitor()
        
        # シミュレートされたメトリクスデータ
        test_scenarios = [
            # 正常な状態
            {"response_time_ms": 200, "error_rate_percent": 1.0, "memory_usage_mb": 30, "cpu_usage_percent": 40},
            {"response_time_ms": 250, "error_rate_percent": 0.5, "memory_usage_mb": 35, "cpu_usage_percent": 45},
            {"response_time_ms": 180, "error_rate_percent": 2.0, "memory_usage_mb": 25, "cpu_usage_percent": 38},
            
            # 警告レベル
            {"response_time_ms": 800, "error_rate_percent": 4.0, "memory_usage_mb": 80, "cpu_usage_percent": 75},
            {"response_time_ms": 900, "error_rate_percent": 4.5, "memory_usage_mb": 85, "cpu_usage_percent": 78},
            
            # 危険レベル
            {"response_time_ms": 1200, "error_rate_percent": 6.0, "memory_usage_mb": 120, "cpu_usage_percent": 85},
            {"response_time_ms": 1500, "error_rate_percent": 8.0, "memory_usage_mb": 150, "cpu_usage_percent": 90},
            
            # 回復
            {"response_time_ms": 300, "error_rate_percent": 2.0, "memory_usage_mb": 40, "cpu_usage_percent": 50},
            {"response_time_ms": 220, "error_rate_percent": 1.5, "memory_usage_mb": 35, "cpu_usage_percent": 45},
        ]
        
        # メトリクス記録
        for scenario in test_scenarios:
            monitor.record_metric(scenario)
            time.sleep(0.01)  # 小さな時間間隔をシミュレート
        
        # 健全性ステータス確認
        health_status = monitor.get_current_health_status()
        
        # アサーション
        assert health_status["status"] in ["healthy", "warning", "critical"], "無効な健全性ステータス"
        assert len(monitor.alerts) > 0, "アラートが発生していない（閾値設定が間違っている可能性）"
        assert health_status["avg_response_time_ms"] > 0, "平均応答時間が記録されていない"
        
        # 高負荷時のアラート確認
        high_load_alerts = [a for a in monitor.alerts if a["value"] > a["threshold"]]
        assert len(high_load_alerts) > 0, "高負荷アラートが正しく検出されていない"
        
        print(f"\n=== リアルタイム性能監視テスト結果 ===")
        print(f"健全性ステータス: {health_status['status']}")
        print(f"平均応答時間: {health_status['avg_response_time_ms']:.1f}ms")
        print(f"平均エラー率: {health_status['avg_error_rate_percent']:.1f}%")
        print(f"総アラート数: {health_status['total_alerts']}")
        print(f"最近のアラート: {len(health_status['recent_alerts'])}件")


if __name__ == "__main__":
    # パフォーマンステストを直接実行する場合の設定
    pytest.main([
        __file__, 
        "-v", 
        "--tb=short", 
        "-m", "performance",
        "--durations=10"
    ])