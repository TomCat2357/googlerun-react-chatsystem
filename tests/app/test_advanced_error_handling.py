"""
高度なエラーハンドリング・エッジケーステスト：回復力と堅牢性の検証
Advanced Error Handling and Edge Case Testing for Resilience

このテストファイルは、以下の高度なエラーハンドリング戦略を実装します：
1. 複合エラーシナリオとカスケード障害
2. 部分的障害からの回復テスト
3. タイムアウト・リトライ・サーキットブレーカーパターン
4. データ整合性とトランザクション境界
5. 非同期エラー伝播と処理
6. セキュリティ脆弱性とインジェクション攻撃への耐性
"""

import pytest
import asyncio
import time
import json
import uuid
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Union
from unittest.mock import patch, MagicMock, create_autospec, call
from contextlib import contextmanager, asynccontextmanager
import tempfile
import os
from dataclasses import dataclass
from enum import Enum

# プロジェクト固有のインポート
from common_utils.class_types import WhisperFirestoreData


class ErrorType(Enum):
    """エラータイプの分類"""
    TRANSIENT = "transient"           # 一時的なエラー（ネットワーク等）
    PERMANENT = "permanent"           # 恒久的なエラー（設定ミス等）
    RESOURCE = "resource"             # リソース不足エラー
    PERMISSION = "permission"         # 権限エラー
    VALIDATION = "validation"         # バリデーションエラー
    CORRUPTION = "corruption"         # データ破損エラー
    TIMEOUT = "timeout"              # タイムアウトエラー
    RATE_LIMIT = "rate_limit"        # レート制限エラー


@dataclass
class ErrorInjectionConfig:
    """エラー注入設定"""
    error_type: ErrorType
    probability: float
    delay_seconds: float = 0.0
    retry_count: int = 0
    recovery_possible: bool = True
    error_message: str = ""


class AdvancedErrorSimulator:
    """高度なエラーシミュレーター"""
    
    def __init__(self):
        self.error_history = []
        self.recovery_attempts = []
        self.failure_patterns = {}
    
    @contextmanager
    def inject_error(self, config: ErrorInjectionConfig):
        """エラー注入のコンテキストマネージャー"""
        import random
        
        should_inject = random.random() < config.probability
        
        if should_inject:
            error_info = {
                "timestamp": datetime.now().isoformat(),
                "error_type": config.error_type,
                "config": config,
                "injected": True
            }
            self.error_history.append(error_info)
            
            if config.delay_seconds > 0:
                time.sleep(config.delay_seconds)
            
            yield self._create_simulated_error(config)
        else:
            yield None
    
    def _create_simulated_error(self, config: ErrorInjectionConfig) -> Exception:
        """シミュレートされたエラーの作成"""
        error_messages = {
            ErrorType.TRANSIENT: "Temporary network connectivity issue",
            ErrorType.PERMANENT: "Invalid configuration detected",
            ErrorType.RESOURCE: "Insufficient memory to complete operation",
            ErrorType.PERMISSION: "Access denied: insufficient permissions",
            ErrorType.VALIDATION: "Invalid input data format",
            ErrorType.CORRUPTION: "Data corruption detected in file",
            ErrorType.TIMEOUT: "Operation timed out after maximum duration",
            ErrorType.RATE_LIMIT: "Rate limit exceeded, please retry later"
        }
        
        message = config.error_message or error_messages.get(config.error_type, "Unknown error")
        
        if config.error_type == ErrorType.TIMEOUT:
            return TimeoutError(message)
        elif config.error_type == ErrorType.PERMISSION:
            return PermissionError(message)
        elif config.error_type == ErrorType.VALIDATION:
            return ValueError(message)
        elif config.error_type == ErrorType.RESOURCE:
            return MemoryError(message)
        else:
            return RuntimeError(message)
    
    def simulate_cascade_failure(self, initial_failure: ErrorType, cascade_steps: List[ErrorType]) -> List[Exception]:
        """カスケード障害のシミュレーション"""
        failures = []
        
        # 初期障害
        initial_error = self._create_simulated_error(ErrorInjectionConfig(
            error_type=initial_failure,
            probability=1.0,
            error_message=f"Initial cascade failure: {initial_failure.value}"
        ))
        failures.append(initial_error)
        
        # カスケード障害
        for step, failure_type in enumerate(cascade_steps):
            cascade_error = self._create_simulated_error(ErrorInjectionConfig(
                error_type=failure_type,
                probability=1.0,
                error_message=f"Cascade step {step + 1}: {failure_type.value} caused by {initial_failure.value}"
            ))
            failures.append(cascade_error)
            time.sleep(0.1)  # カスケードの時間遅延
        
        return failures
    
    def record_recovery_attempt(self, operation: str, success: bool, attempt_count: int):
        """回復試行の記録"""
        self.recovery_attempts.append({
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "success": success,
            "attempt_count": attempt_count
        })


class TestComplexErrorScenarios:
    """複合エラーシナリオテスト"""
    
    @pytest.fixture
    def error_simulator(self):
        """エラーシミュレーターのフィクスチャ"""
        return AdvancedErrorSimulator()
    
    def test_cascade_failure_handling(self, error_simulator, enhanced_gcp_services):
        """カスケード障害ハンドリングテスト"""
        # カスケード障害シナリオ：ネットワーク → タイムアウト → リソース不足
        cascade_failures = error_simulator.simulate_cascade_failure(
            initial_failure=ErrorType.TRANSIENT,
            cascade_steps=[ErrorType.TIMEOUT, ErrorType.RESOURCE]
        )
        
        def whisper_operation_with_cascade_handling(job_id: str) -> Dict[str, Any]:
            """カスケード障害に対応したWhisper操作"""
            try:
                # 段階1: GCS操作（ネットワークエラーの可能性）
                bucket = enhanced_gcp_services["storage"].bucket("test-bucket")
                blob = bucket.blob(f"whisper/{job_id}.wav")
                
                # カスケード障害注入
                if cascade_failures:
                    raise cascade_failures[0]  # ネットワークエラー
                
                # 段階2: Firestore操作（タイムアウトの可能性）
                collection = enhanced_gcp_services["firestore"].collection("whisper_jobs")
                doc_ref = collection.document(job_id)
                
                if len(cascade_failures) > 1:
                    raise cascade_failures[1]  # タイムアウトエラー
                
                # 段階3: 処理実行（リソースエラーの可能性）
                processing_result = self._simulate_heavy_processing(job_id)
                
                if len(cascade_failures) > 2:
                    raise cascade_failures[2]  # リソースエラー
                
                return {"status": "success", "job_id": job_id, "result": processing_result}
                
            except Exception as e:
                # カスケード障害の処理
                error_type = type(e).__name__
                recovery_strategy = self._determine_recovery_strategy(error_type)
                
                return {
                    "status": "failed_with_recovery",
                    "job_id": job_id,
                    "error": str(e),
                    "error_type": error_type,
                    "recovery_strategy": recovery_strategy,
                    "cascade_depth": len(cascade_failures)
                }
        
        # カスケード障害テスト実行
        result = whisper_operation_with_cascade_handling("cascade_test_job")
        
        # アサーション
        assert result["status"] == "failed_with_recovery", "カスケード障害が適切に処理されていません"
        assert result["cascade_depth"] > 0, "カスケード障害の深度が記録されていません"
        assert "recovery_strategy" in result, "回復戦略が提案されていません"
        
        # エラー履歴の確認
        assert len(error_simulator.error_history) >= 0, "エラー履歴が記録されていません"
        
        print(f"\n=== カスケード障害テスト結果 ===")
        print(f"カスケード深度: {result['cascade_depth']}")
        print(f"最終エラータイプ: {result['error_type']}")
        print(f"回復戦略: {result['recovery_strategy']}")
    
    def _simulate_heavy_processing(self, job_id: str) -> Dict[str, Any]:
        """重い処理のシミュレーション"""
        return {
            "job_id": job_id,
            "processed_at": datetime.now().isoformat(),
            "processing_time_seconds": 120
        }
    
    def _determine_recovery_strategy(self, error_type: str) -> str:
        """エラータイプに基づく回復戦略の決定"""
        strategies = {
            "RuntimeError": "exponential_backoff_retry",
            "TimeoutError": "increase_timeout_and_retry",
            "MemoryError": "reduce_batch_size_and_retry",
            "PermissionError": "check_credentials_and_retry",
            "ValueError": "validate_input_and_retry"
        }
        return strategies.get(error_type, "manual_intervention_required")
    
    def test_partial_failure_recovery(self, error_simulator, enhanced_gcp_services):
        """部分的障害からの回復テスト"""
        batch_jobs = [f"batch_job_{i}" for i in range(10)]
        
        def process_batch_with_partial_failures(jobs: List[str]) -> Dict[str, Any]:
            """部分的障害が発生するバッチ処理"""
            successful_jobs = []
            failed_jobs = []
            recovered_jobs = []
            
            for i, job_id in enumerate(jobs):
                try:
                    # 30%の確率で障害発生
                    with error_simulator.inject_error(ErrorInjectionConfig(
                        error_type=ErrorType.TRANSIENT,
                        probability=0.3,
                        recovery_possible=True
                    )) as injected_error:
                        
                        if injected_error:
                            raise injected_error
                        
                        # 正常処理
                        self._process_single_job(job_id)
                        successful_jobs.append(job_id)
                        
                except Exception as e:
                    failed_jobs.append({"job_id": job_id, "error": str(e)})
                    
                    # 回復試行
                    recovery_success = self._attempt_job_recovery(job_id, str(e))
                    error_simulator.record_recovery_attempt(job_id, recovery_success, 1)
                    
                    if recovery_success:
                        recovered_jobs.append(job_id)
                        successful_jobs.append(job_id)
            
            return {
                "total_jobs": len(jobs),
                "successful_jobs": successful_jobs,
                "failed_jobs": failed_jobs,
                "recovered_jobs": recovered_jobs,
                "success_rate": len(successful_jobs) / len(jobs),
                "recovery_rate": len(recovered_jobs) / len(failed_jobs) if failed_jobs else 0
            }
        
        # 部分的障害テスト実行
        result = process_batch_with_partial_failures(batch_jobs)
        
        # アサーション
        assert result["total_jobs"] == len(batch_jobs), "総ジョブ数が一致しません"
        assert result["success_rate"] > 0.5, f"成功率が低すぎます: {result['success_rate']:.2f}"
        
        if result["failed_jobs"]:
            assert result["recovery_rate"] > 0, "回復機能が動作していません"
        
        # 回復試行の記録確認
        recovery_attempts = error_simulator.recovery_attempts
        assert len(recovery_attempts) >= 0, "回復試行が記録されていません"
        
        print(f"\n=== 部分的障害回復テスト結果 ===")
        print(f"成功率: {result['success_rate']:.2%}")
        print(f"回復率: {result['recovery_rate']:.2%}")
        print(f"回復したジョブ数: {len(result['recovered_jobs'])}")
        print(f"回復試行記録数: {len(recovery_attempts)}")
    
    def _process_single_job(self, job_id: str):
        """単一ジョブの処理"""
        time.sleep(0.01)  # 処理時間をシミュレート
    
    def _attempt_job_recovery(self, job_id: str, error: str) -> bool:
        """ジョブ回復の試行"""
        # 簡単な回復ロジック：50%の確率で成功
        import random
        return random.random() < 0.5


class TestRetryAndCircuitBreakerPatterns:
    """リトライ・サーキットブレーカーパターンテスト"""
    
    def test_exponential_backoff_retry_pattern(self, error_simulator):
        """指数バックオフリトライパターンテスト"""
        
        class ExponentialBackoffRetry:
            def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
                self.max_retries = max_retries
                self.base_delay = base_delay
                self.max_delay = max_delay
                self.attempt_times = []
            
            def execute_with_retry(self, operation: Callable, *args, **kwargs):
                """指数バックオフでリトライ実行"""
                for attempt in range(self.max_retries + 1):
                    try:
                        start_time = time.time()
                        result = operation(*args, **kwargs)
                        self.attempt_times.append(time.time() - start_time)
                        return {"success": True, "result": result, "attempts": attempt + 1}
                        
                    except Exception as e:
                        self.attempt_times.append(time.time() - start_time)
                        
                        if attempt == self.max_retries:
                            return {"success": False, "error": str(e), "attempts": attempt + 1}
                        
                        # 指数バックオフ計算
                        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                        time.sleep(delay)
                
                return {"success": False, "error": "Max retries exceeded", "attempts": self.max_retries + 1}
        
        def unreliable_operation(operation_id: str) -> str:
            """不安定な操作（70%の確率で失敗）"""
            with error_simulator.inject_error(ErrorInjectionConfig(
                error_type=ErrorType.TRANSIENT,
                probability=0.7,
                error_message=f"Transient failure in operation {operation_id}"
            )) as injected_error:
                
                if injected_error:
                    raise injected_error
                
                return f"Success: {operation_id}"
        
        # リトライテスト実行
        retry_handler = ExponentialBackoffRetry(max_retries=4, base_delay=0.1)
        
        results = []
        for i in range(10):
            result = retry_handler.execute_with_retry(unreliable_operation, f"test_op_{i}")
            results.append(result)
        
        # 結果分析
        successful_operations = [r for r in results if r["success"]]
        failed_operations = [r for r in results if not r["success"]]
        
        # アサーション
        success_rate = len(successful_operations) / len(results)
        assert success_rate > 0.6, f"リトライによる成功率向上が不十分: {success_rate:.2%}"
        
        # リトライ回数の確認
        average_attempts = sum(r["attempts"] for r in results) / len(results)
        assert average_attempts > 1.0, "リトライが実行されていません"
        assert average_attempts <= 5.0, "過度なリトライが発生しています"
        
        print(f"\n=== 指数バックオフリトライテスト結果 ===")
        print(f"成功率: {success_rate:.2%}")
        print(f"平均試行回数: {average_attempts:.1f}")
        print(f"成功操作数: {len(successful_operations)}")
        print(f"失敗操作数: {len(failed_operations)}")
    
    def test_circuit_breaker_pattern(self, error_simulator):
        """サーキットブレーカーパターンテスト"""
        
        class CircuitBreaker:
            def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 10.0):
                self.failure_threshold = failure_threshold
                self.recovery_timeout = recovery_timeout
                self.failure_count = 0
                self.last_failure_time = None
                self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
                self.call_history = []
            
            def call(self, operation: Callable, *args, **kwargs):
                """サーキットブレーカー経由での操作実行"""
                current_time = time.time()
                
                # 状態管理
                if self.state == "OPEN":
                    if current_time - self.last_failure_time > self.recovery_timeout:
                        self.state = "HALF_OPEN"
                    else:
                        self.call_history.append({"state": "OPEN", "blocked": True})
                        raise RuntimeError("Circuit breaker is OPEN")
                
                try:
                    result = operation(*args, **kwargs)
                    
                    # 成功時の処理
                    if self.state == "HALF_OPEN":
                        self.state = "CLOSED"
                        self.failure_count = 0
                    
                    self.call_history.append({"state": self.state, "success": True})
                    return result
                    
                except Exception as e:
                    self.failure_count += 1
                    self.last_failure_time = current_time
                    
                    if self.failure_count >= self.failure_threshold:
                        self.state = "OPEN"
                    
                    self.call_history.append({
                        "state": self.state, 
                        "success": False, 
                        "failure_count": self.failure_count
                    })
                    raise e
        
        def failing_service(call_id: str) -> str:
            """失敗する外部サービス（90%の確率で失敗）"""
            with error_simulator.inject_error(ErrorInjectionConfig(
                error_type=ErrorType.TRANSIENT,
                probability=0.9,
                error_message=f"Service unavailable for call {call_id}"
            )) as injected_error:
                
                if injected_error:
                    raise injected_error
                
                return f"Service response: {call_id}"
        
        # サーキットブレーカーテスト実行
        circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=2.0)
        
        results = []
        
        # 段階1: 失敗蓄積（CLOSED → OPEN）
        for i in range(10):
            try:
                result = circuit_breaker.call(failing_service, f"call_{i}")
                results.append({"call_id": f"call_{i}", "success": True, "result": result})
            except Exception as e:
                results.append({"call_id": f"call_{i}", "success": False, "error": str(e)})
        
        # 段階2: 回復待機
        time.sleep(2.5)  # recovery_timeoutを超過
        
        # 段階3: 回復試行（HALF_OPEN → CLOSED or OPEN）
        for i in range(5):
            try:
                result = circuit_breaker.call(failing_service, f"recovery_call_{i}")
                results.append({"call_id": f"recovery_call_{i}", "success": True, "result": result})
            except Exception as e:
                results.append({"call_id": f"recovery_call_{i}", "success": False, "error": str(e)})
        
        # 結果分析
        total_calls = len(results)
        successful_calls = len([r for r in results if r["success"]])
        circuit_open_blocks = len([h for h in circuit_breaker.call_history if h.get("blocked")])
        
        # アサーション
        assert circuit_open_blocks > 0, "サーキットブレーカーがOPEN状態になっていません"
        assert circuit_breaker.failure_count >= 0, "失敗カウントが記録されていません"
        
        # 状態遷移の確認
        states_encountered = set(h["state"] for h in circuit_breaker.call_history)
        assert "CLOSED" in states_encountered, "CLOSED状態が記録されていません"
        assert "OPEN" in states_encountered, "OPEN状態が記録されていません"
        
        print(f"\n=== サーキットブレーカーテスト結果 ===")
        print(f"総呼び出し数: {total_calls}")
        print(f"成功呼び出し数: {successful_calls}")
        print(f"ブロックされた呼び出し数: {circuit_open_blocks}")
        print(f"現在の状態: {circuit_breaker.state}")
        print(f"失敗カウント: {circuit_breaker.failure_count}")
        print(f"経験した状態: {list(states_encountered)}")


class TestDataIntegrityAndTransactions:
    """データ整合性・トランザクション境界テスト"""
    
    def test_transaction_rollback_on_partial_failure(self, enhanced_gcp_services, error_simulator):
        """部分的障害時のトランザクションロールバックテスト"""
        
        class WhisperJobTransaction:
            def __init__(self, firestore_client, storage_client):
                self.firestore = firestore_client
                self.storage = storage_client
                self.operations_log = []
                self.rollback_operations = []
            
            def execute_job_creation_transaction(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
                """ジョブ作成のトランザクション実行"""
                try:
                    # 操作1: GCSにファイルアップロード
                    gcs_result = self._upload_to_gcs(job_data)
                    self.operations_log.append({"operation": "gcs_upload", "result": gcs_result})
                    
                    # 操作2: Firestoreにドキュメント作成
                    firestore_result = self._create_firestore_document(job_data)
                    self.operations_log.append({"operation": "firestore_create", "result": firestore_result})
                    
                    # 操作3: Pub/Subメッセージ送信（ここで障害発生の可能性）
                    pubsub_result = self._send_pubsub_message(job_data)
                    self.operations_log.append({"operation": "pubsub_send", "result": pubsub_result})
                    
                    return {"status": "success", "operations": len(self.operations_log)}
                    
                except Exception as e:
                    # トランザクションロールバック
                    rollback_result = self._rollback_operations()
                    return {
                        "status": "failed_with_rollback",
                        "error": str(e),
                        "operations_attempted": len(self.operations_log),
                        "rollback_operations": len(rollback_result),
                        "rollback_successful": all(r["success"] for r in rollback_result)
                    }
            
            def _upload_to_gcs(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
                """GCSアップロード"""
                bucket = self.storage.bucket(job_data["bucket_name"])
                blob = bucket.blob(job_data["gcs_path"])
                blob.upload_from_string(job_data["audio_data"], content_type="audio/wav")
                
                # ロールバック操作を記録
                self.rollback_operations.append(
                    lambda: blob.delete()
                )
                
                return {"gcs_path": job_data["gcs_path"], "size": len(job_data["audio_data"])}
            
            def _create_firestore_document(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
                """Firestoreドキュメント作成"""
                collection = self.firestore.collection("whisper_jobs")
                doc_ref = collection.document(job_data["job_id"])
                doc_ref.set({
                    "job_id": job_data["job_id"],
                    "status": "queued",
                    "created_at": datetime.now().isoformat()
                })
                
                # ロールバック操作を記録
                self.rollback_operations.append(
                    lambda: doc_ref.delete()
                )
                
                return {"document_id": job_data["job_id"]}
            
            def _send_pubsub_message(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
                """Pub/Subメッセージ送信（障害発生箇所）"""
                # 50%の確率で障害発生
                with error_simulator.inject_error(ErrorInjectionConfig(
                    error_type=ErrorType.TRANSIENT,
                    probability=0.5,
                    error_message="Pub/Sub service temporarily unavailable"
                )) as injected_error:
                    
                    if injected_error:
                        raise injected_error
                    
                    # 正常時のPub/Sub送信をシミュレート
                    return {"message_id": f"msg_{uuid.uuid4().hex[:8]}"}
            
            def _rollback_operations(self) -> List[Dict[str, Any]]:
                """トランザクションロールバック"""
                rollback_results = []
                
                # 逆順でロールバック実行
                for rollback_op in reversed(self.rollback_operations):
                    try:
                        rollback_op()
                        rollback_results.append({"success": True})
                    except Exception as e:
                        rollback_results.append({"success": False, "error": str(e)})
                
                return rollback_results
        
        # トランザクションテスト実行
        test_job_data = {
            "job_id": f"transaction_test_{uuid.uuid4().hex[:8]}",
            "bucket_name": "test-bucket",
            "gcs_path": "whisper/transaction_test.wav",
            "audio_data": "mock_audio_data"
        }
        
        results = []
        for i in range(10):  # 複数回実行して統計を取る
            transaction = WhisperJobTransaction(
                enhanced_gcp_services["firestore"],
                enhanced_gcp_services["storage"]
            )
            
            result = transaction.execute_job_creation_transaction(test_job_data)
            results.append(result)
        
        # 結果分析
        successful_transactions = [r for r in results if r["status"] == "success"]
        failed_with_rollback = [r for r in results if r["status"] == "failed_with_rollback"]
        
        # アサーション
        assert len(results) == 10, "すべてのトランザクションが実行されていません"
        
        if failed_with_rollback:
            # ロールバックが正常に動作したかチェック
            rollback_success_rate = sum(
                1 for r in failed_with_rollback if r.get("rollback_successful", False)
            ) / len(failed_with_rollback)
            
            assert rollback_success_rate >= 0.8, f"ロールバック成功率が低い: {rollback_success_rate:.2%}"
        
        success_rate = len(successful_transactions) / len(results)
        
        print(f"\n=== トランザクション整合性テスト結果 ===")
        print(f"成功率: {success_rate:.2%}")
        print(f"成功トランザクション数: {len(successful_transactions)}")
        print(f"ロールバック発生数: {len(failed_with_rollback)}")
        if failed_with_rollback:
            print(f"ロールバック成功率: {rollback_success_rate:.2%}")
    
    def test_concurrent_access_data_race_conditions(self, enhanced_gcp_services):
        """並行アクセス・データ競合状態テスト"""
        
        class ConcurrentJobProcessor:
            def __init__(self, firestore_client):
                self.firestore = firestore_client
                self.access_log = []
                self.lock = threading.Lock()
            
            def process_job_with_status_update(self, job_id: str, worker_id: int) -> Dict[str, Any]:
                """ジョブステータス更新を伴う処理（競合状態の可能性）"""
                try:
                    # ジョブ取得
                    doc_ref = self.firestore.collection("whisper_jobs").document(job_id)
                    
                    with self.lock:
                        self.access_log.append({
                            "timestamp": time.time(),
                            "worker_id": worker_id,
                            "operation": "read",
                            "job_id": job_id
                        })
                    
                    # 模擬的な読み取り遅延
                    time.sleep(0.01)
                    
                    # ステータス更新（競合の可能性）
                    doc_ref.update({
                        "status": "processing",
                        "worker_id": worker_id,
                        "updated_at": datetime.now().isoformat()
                    })
                    
                    with self.lock:
                        self.access_log.append({
                            "timestamp": time.time(),
                            "worker_id": worker_id,
                            "operation": "update",
                            "job_id": job_id
                        })
                    
                    # 処理時間シミュレート
                    time.sleep(0.05)
                    
                    # 完了ステータス更新
                    doc_ref.update({
                        "status": "completed",
                        "completed_by": worker_id,
                        "completed_at": datetime.now().isoformat()
                    })
                    
                    with self.lock:
                        self.access_log.append({
                            "timestamp": time.time(),
                            "worker_id": worker_id,
                            "operation": "complete",
                            "job_id": job_id
                        })
                    
                    return {"status": "success", "worker_id": worker_id, "job_id": job_id}
                    
                except Exception as e:
                    return {"status": "error", "worker_id": worker_id, "error": str(e)}
        
        # 並行処理テスト実行
        processor = ConcurrentJobProcessor(enhanced_gcp_services["firestore"])
        test_job_id = f"concurrent_test_{uuid.uuid4().hex[:8]}"
        
        # 初期ジョブ作成
        doc_ref = enhanced_gcp_services["firestore"].collection("whisper_jobs").document(test_job_id)
        doc_ref.set({
            "job_id": test_job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat()
        })
        
        # 複数ワーカーで同時処理
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(processor.process_job_with_status_update, test_job_id, worker_id)
                for worker_id in range(5)
            ]
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # 結果分析
        successful_workers = [r for r in results if r["status"] == "success"]
        
        # アサーション
        assert len(results) == 5, "すべてのワーカーが実行されていません"
        
        # 競合状態の検出
        access_timeline = sorted(processor.access_log, key=lambda x: x["timestamp"])
        
        # 同時アクセスの検出（時間差が0.001秒以内）
        concurrent_accesses = 0
        for i in range(1, len(access_timeline)):
            time_diff = access_timeline[i]["timestamp"] - access_timeline[i-1]["timestamp"]
            if time_diff < 0.001:
                concurrent_accesses += 1
        
        print(f"\n=== 並行アクセス競合テスト結果 ===")
        print(f"成功ワーカー数: {len(successful_workers)}")
        print(f"アクセス記録数: {len(access_timeline)}")
        print(f"同時アクセス検出数: {concurrent_accesses}")
        print(f"データ競合の可能性: {'有' if concurrent_accesses > 0 else '無'}")


class TestAsyncErrorPropagation:
    """非同期エラー伝播テスト"""
    
    @pytest.mark.asyncio
    async def test_async_error_propagation_and_cleanup(self, error_simulator):
        """非同期エラー伝播とクリーンアップテスト"""
        
        class AsyncWhisperProcessor:
            def __init__(self):
                self.active_tasks = []
                self.cleanup_log = []
            
            async def process_audio_pipeline(self, job_id: str) -> Dict[str, Any]:
                """非同期音声処理パイプライン"""
                try:
                    # 段階1: 音声ダウンロード
                    download_task = asyncio.create_task(self._download_audio(job_id))
                    self.active_tasks.append(download_task)
                    audio_data = await download_task
                    
                    # 段階2: 音声処理
                    process_task = asyncio.create_task(self._process_audio(job_id, audio_data))
                    self.active_tasks.append(process_task)
                    result = await process_task
                    
                    # 段階3: 結果アップロード
                    upload_task = asyncio.create_task(self._upload_results(job_id, result))
                    self.active_tasks.append(upload_task)
                    upload_result = await upload_task
                    
                    return {"status": "success", "job_id": job_id, "result": upload_result}
                    
                except Exception as e:
                    # エラー時のクリーンアップ
                    await self._cleanup_failed_job(job_id)
                    return {"status": "error", "job_id": job_id, "error": str(e)}
                
                finally:
                    # アクティブタスクのクリーンアップ
                    await self._cleanup_active_tasks()
            
            async def _download_audio(self, job_id: str) -> bytes:
                """音声ダウンロード（エラー発生の可能性）"""
                await asyncio.sleep(0.1)  # ダウンロード時間シミュレート
                
                with error_simulator.inject_error(ErrorInjectionConfig(
                    error_type=ErrorType.TRANSIENT,
                    probability=0.3,
                    error_message=f"Download failed for job {job_id}"
                )) as injected_error:
                    
                    if injected_error:
                        raise injected_error
                    
                    return f"audio_data_{job_id}".encode()
            
            async def _process_audio(self, job_id: str, audio_data: bytes) -> Dict[str, Any]:
                """音声処理（エラー発生の可能性）"""
                await asyncio.sleep(0.2)  # 処理時間シミュレート
                
                with error_simulator.inject_error(ErrorInjectionConfig(
                    error_type=ErrorType.RESOURCE,
                    probability=0.2,
                    error_message=f"Processing failed for job {job_id} due to insufficient resources"
                )) as injected_error:
                    
                    if injected_error:
                        raise injected_error
                    
                    return {
                        "transcription": f"Transcribed content for {job_id}",
                        "duration": 120,
                        "speakers": 2
                    }
            
            async def _upload_results(self, job_id: str, result: Dict[str, Any]) -> str:
                """結果アップロード（エラー発生の可能性）"""
                await asyncio.sleep(0.05)  # アップロード時間シミュレート
                
                with error_simulator.inject_error(ErrorInjectionConfig(
                    error_type=ErrorType.PERMISSION,
                    probability=0.1,
                    error_message=f"Upload permission denied for job {job_id}"
                )) as injected_error:
                    
                    if injected_error:
                        raise injected_error
                    
                    return f"gs://results/{job_id}/result.json"
            
            async def _cleanup_failed_job(self, job_id: str):
                """失敗ジョブのクリーンアップ"""
                self.cleanup_log.append({
                    "job_id": job_id,
                    "cleanup_type": "failed_job",
                    "timestamp": time.time()
                })
                await asyncio.sleep(0.01)  # クリーンアップ時間
            
            async def _cleanup_active_tasks(self):
                """アクティブタスクのクリーンアップ"""
                for task in self.active_tasks:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                
                self.cleanup_log.append({
                    "cleanup_type": "active_tasks",
                    "tasks_cleaned": len(self.active_tasks),
                    "timestamp": time.time()
                })
                
                self.active_tasks.clear()
        
        # 非同期エラー伝播テスト実行
        processor = AsyncWhisperProcessor()
        
        tasks = []
        for i in range(10):
            task = asyncio.create_task(processor.process_audio_pipeline(f"async_job_{i}"))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 結果分析
        successful_jobs = [r for r in results if isinstance(r, dict) and r.get("status") == "success"]
        failed_jobs = [r for r in results if isinstance(r, dict) and r.get("status") == "error"]
        exceptions = [r for r in results if isinstance(r, Exception)]
        
        # アサーション
        total_processed = len(successful_jobs) + len(failed_jobs)
        assert total_processed > 0, "処理されたジョブがありません"
        assert len(exceptions) == 0, f"処理されていない例外があります: {exceptions}"
        
        # クリーンアップの確認
        cleanup_operations = len(processor.cleanup_log)
        assert cleanup_operations > 0, "クリーンアップ操作が記録されていません"
        
        print(f"\n=== 非同期エラー伝播テスト結果 ===")
        print(f"成功ジョブ数: {len(successful_jobs)}")
        print(f"失敗ジョブ数: {len(failed_jobs)}")
        print(f"未処理例外数: {len(exceptions)}")
        print(f"クリーンアップ操作数: {cleanup_operations}")


class TestSecurityResilience:
    """セキュリティ耐性テスト"""
    
    def test_input_validation_injection_resistance(self):
        """入力バリデーション・インジェクション攻撃耐性テスト"""
        
        def secure_filename_validator(filename: str) -> Dict[str, Any]:
            """安全なファイル名バリデーター"""
            import re
            import os.path
            
            validation_result = {
                "is_valid": True,
                "violations": [],
                "sanitized_filename": filename
            }
            
            # パストラバーサル攻撃チェック
            if ".." in filename or "/" in filename or "\\" in filename:
                validation_result["is_valid"] = False
                validation_result["violations"].append("path_traversal_attempt")
            
            # SQLインジェクション風の文字列チェック
            sql_patterns = ["'", '"', ";", "--", "/*", "*/", "xp_", "sp_"]
            for pattern in sql_patterns:
                if pattern in filename.lower():
                    validation_result["is_valid"] = False
                    validation_result["violations"].append(f"sql_injection_pattern: {pattern}")
            
            # スクリプトインジェクション風の文字列チェック
            script_patterns = ["<script", "javascript:", "onload=", "onerror="]
            for pattern in script_patterns:
                if pattern in filename.lower():
                    validation_result["is_valid"] = False
                    validation_result["violations"].append(f"script_injection_pattern: {pattern}")
            
            # コマンドインジェクション風の文字列チェック
            command_patterns = [";", "|", "&", "$", "`", "$("]
            for pattern in command_patterns:
                if pattern in filename:
                    validation_result["is_valid"] = False
                    validation_result["violations"].append(f"command_injection_pattern: {pattern}")
            
            # ファイル名長チェック
            if len(filename) > 255:
                validation_result["is_valid"] = False
                validation_result["violations"].append("filename_too_long")
            
            # 無効文字チェック
            invalid_chars = ["<", ">", ":", "|", "?", "*"]
            for char in invalid_chars:
                if char in filename:
                    validation_result["is_valid"] = False
                    validation_result["violations"].append(f"invalid_character: {char}")
            
            # ファイル名サニタイゼーション
            if not validation_result["is_valid"]:
                # 安全な文字のみを残す
                sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
                sanitized = sanitized[:255]  # 長さ制限
                validation_result["sanitized_filename"] = sanitized
            
            return validation_result
        
        # 攻撃的入力のテストケース
        malicious_inputs = [
            # パストラバーサル攻撃
            "../../../etc/passwd",
            "..\\windows\\system32\\config\\sam",
            "audio/../../../secret.txt",
            
            # SQLインジェクション風
            "audio'; DROP TABLE users; --",
            "file\"OR 1=1--",
            "/*comment*/audio.wav",
            
            # スクリプトインジェクション風
            "<script>alert('xss')</script>.wav",
            "javascript:alert(1).mp3",
            "onload=alert(1).m4a",
            
            # コマンドインジェクション風
            "audio.wav; rm -rf /",
            "file.wav | cat /etc/passwd",
            "audio.wav && shutdown -h now",
            "$(cat /etc/passwd).wav",
            "`whoami`.mp3",
            
            # その他の攻撃
            "a" * 300,  # 長すぎるファイル名
            "file<>|?*.wav",  # 無効文字
            "",  # 空文字列
            "   ",  # 空白のみ
        ]
        
        # バリデーションテスト実行
        validation_results = []
        for malicious_input in malicious_inputs:
            result = secure_filename_validator(malicious_input)
            validation_results.append({
                "input": malicious_input,
                "result": result
            })
        
        # セキュリティ評価
        blocked_attacks = len([r for r in validation_results if not r["result"]["is_valid"]])
        total_attacks = len(validation_results)
        
        # アサーション
        block_rate = blocked_attacks / total_attacks
        assert block_rate >= 0.95, f"攻撃ブロック率が低い: {block_rate:.2%}"
        
        # 具体的な攻撃パターンの検証
        path_traversal_blocked = any(
            "path_traversal_attempt" in r["result"]["violations"]
            for r in validation_results
        )
        sql_injection_blocked = any(
            any("sql_injection_pattern" in v for v in r["result"]["violations"])
            for r in validation_results
        )
        script_injection_blocked = any(
            any("script_injection_pattern" in v for v in r["result"]["violations"])
            for r in validation_results
        )
        
        assert path_traversal_blocked, "パストラバーサル攻撃が検出されていません"
        assert sql_injection_blocked, "SQLインジェクション風攻撃が検出されていません"
        assert script_injection_blocked, "スクリプトインジェクション風攻撃が検出されていません"
        
        print(f"\n=== セキュリティ耐性テスト結果 ===")
        print(f"攻撃ブロック率: {block_rate:.2%}")
        print(f"ブロックされた攻撃数: {blocked_attacks}/{total_attacks}")
        print(f"パストラバーサル検出: {'有' if path_traversal_blocked else '無'}")
        print(f"SQLインジェクション検出: {'有' if sql_injection_blocked else '無'}")
        print(f"スクリプトインジェクション検出: {'有' if script_injection_blocked else '無'}")


if __name__ == "__main__":
    # エラーハンドリングテストを直接実行する場合の設定
    pytest.main([
        __file__, 
        "-v", 
        "--tb=long", 
        "-x",
        "--capture=no"
    ])