"""
GCPエミュレータの利用可能性テスト

このファイルでは、テスト時に必要なGCPエミュレータが
適切に利用可能かどうかを確認します。
"""

import pytest
import subprocess
import shutil
from unittest.mock import patch

from common_utils.gcp_emulator import (
    FirestoreEmulator, 
    GCSEmulator,
    firestore_emulator_context,
    gcs_emulator_context
)


class TestEmulatorAvailability:
    """エミュレータの利用可能性テスト"""
    
    def test_firestore_emulator_dependencies(self):
        """Firestoreエミュレータの依存関係チェック"""
        # gcloudコマンドの確認
        gcloud_available = shutil.which('gcloud') is not None
        assert gcloud_available, "gcloudコマンドが見つかりません。Google Cloud SDKをインストールしてください。"
        
        # gcloud betaコンポーネントの確認
        try:
            result = subprocess.run(
                ['gcloud', 'components', 'list', '--filter=beta', '--format=value(name)'],
                capture_output=True, text=True, timeout=10
            )
            beta_available = 'beta' in result.stdout
            if not beta_available:
                pytest.skip("gcloud betaコンポーネントが利用できません。")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("gcloudコマンドの実行に失敗しました。")
    
    def test_gcs_emulator_dependencies(self):
        """GCSエミュレータの依存関係チェック"""
        # Dockerの確認
        docker_available = shutil.which('docker') is not None
        
        if not docker_available:
            pytest.skip("Dockerが利用できません。GCSエミュレータはスキップされます。")
        
        # Dockerデーモンの動作確認
        try:
            result = subprocess.run(
                ['docker', 'info'], 
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                pytest.skip("Dockerデーモンが動作していません。")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Dockerの動作確認に失敗しました。")
    
    @pytest.mark.asyncio
    async def test_firestore_emulator_functionality(self):
        """Firestoreエミュレータの機能テスト"""
        try:
            with firestore_emulator_context(
                port=8094,
                project_id='test-functionality'
            ) as emulator:
                assert emulator.is_running()
                assert emulator.project_id == 'test-functionality'
                
                # 環境変数が正しく設定されているかチェック
                import os
                assert 'FIRESTORE_EMULATOR_HOST' in os.environ
                assert 'localhost:8094' in os.environ['FIRESTORE_EMULATOR_HOST']
                
        except Exception as e:
            pytest.fail(f"Firestoreエミュレータの機能テストに失敗: {e}")
    
    @pytest.mark.asyncio
    async def test_gcs_emulator_functionality_if_available(self):
        """GCSエミュレータの機能テスト（利用可能な場合のみ）"""
        docker_available = shutil.which('docker') is not None
        
        if not docker_available:
            pytest.skip("Dockerが利用できないため、GCSエミュレータテストをスキップします。")
        
        try:
            # Dockerデーモンの動作確認
            result = subprocess.run(
                ['docker', 'info'], 
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                pytest.skip("Dockerデーモンが動作していないため、GCSエミュレータテストをスキップします。")
        except:
            pytest.skip("Docker動作確認に失敗したため、GCSエミュレータテストをスキップします。")
        
        try:
            with gcs_emulator_context(
                port=9094,
                project_id='test-gcs-functionality'
            ) as emulator:
                assert emulator.is_running()
                assert emulator.project_id == 'test-gcs-functionality'
                
                # 環境変数が正しく設定されているかチェック
                import os
                assert 'STORAGE_EMULATOR_HOST' in os.environ
                
        except Exception as e:
            pytest.fail(f"GCSエミュレータの機能テストに失敗: {e}")


class TestEmulatorCompatibility:
    """エミュレータ互換性テスト"""
    
    def test_emulator_import_compatibility(self):
        """エミュレータモジュールのインポート互換性"""
        # 基本的なインポートテスト
        try:
            from common_utils.gcp_emulator import (
                EmulatorManager,
                FirestoreEmulator,
                GCSEmulator,
                firestore_emulator_context,
                gcs_emulator_context
            )
        except ImportError as e:
            pytest.fail(f"エミュレータモジュールのインポートに失敗: {e}")
    
    def test_google_cloud_libraries_availability(self):
        """Google Cloudライブラリの利用可能性"""
        try:
            import google.cloud.firestore
            import google.cloud.storage
        except ImportError:
            pytest.skip("Google Cloudライブラリが利用できません。")
    
    def test_emulator_configuration_validation(self):
        """エミュレータ設定の検証"""
        # Firestoreエミュレータの設定
        fs_emulator = FirestoreEmulator(
            host='localhost',
            port=8095,
            project_id='test-config'
        )
        
        assert fs_emulator.host == 'localhost'
        assert fs_emulator.port == 8095
        assert fs_emulator.project_id == 'test-config'
        assert fs_emulator.emulator_host_env == 'localhost:8095'
        
        # GCSエミュレータの設定
        gcs_emulator = GCSEmulator(
            host='localhost',
            port=9095,
            project_id='test-gcs-config'
        )
        
        assert gcs_emulator.host == 'localhost'
        assert gcs_emulator.port == 9095
        assert gcs_emulator.project_id == 'test-gcs-config'
        assert gcs_emulator.emulator_host_env == 'http://localhost:9095'


class TestEmulatorIntegrationGuidance:
    """エミュレータ統合ガイダンス"""
    
    def test_emulator_usage_documentation(self):
        """エミュレータ使用方法のドキュメント確認"""
        
        # 必要なファイルが存在することを確認
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        
        # エミュレータ実行スクリプトの存在確認
        gcp_emulator_script = project_root / "tests" / "app" / "gcp_emulator_run.py"
        assert gcp_emulator_script.exists(), "GCPエミュレータ実行スクリプトが見つかりません"
        
        # エミュレータテスト例の存在確認
        emulator_example = project_root / "tests" / "app" / "test_whisper_emulator_example.py"
        assert emulator_example.exists(), "エミュレータテスト例ファイルが見つかりません"
    
    def test_emulator_environment_variables(self):
        """エミュレータ環境変数のテスト"""
        import os
        
        # テスト前の環境変数状態を記録
        original_firestore_host = os.environ.get('FIRESTORE_EMULATOR_HOST')
        original_storage_host = os.environ.get('STORAGE_EMULATOR_HOST')
        
        try:
            # Firestoreエミュレータの環境変数設定テスト
            fs_emulator = FirestoreEmulator(port=8096, project_id='test-env')
            fs_emulator._set_env_vars()
            
            assert os.environ.get('FIRESTORE_EMULATOR_HOST') == 'localhost:8096'
            
            fs_emulator._unset_env_vars()
            assert os.environ.get('FIRESTORE_EMULATOR_HOST') is None
            
            # GCSエミュレータの環境変数設定テスト
            gcs_emulator = GCSEmulator(port=9096, project_id='test-gcs-env')
            gcs_emulator._set_env_vars()
            
            assert os.environ.get('STORAGE_EMULATOR_HOST') == 'http://localhost:9096'
            assert os.environ.get('GOOGLE_CLOUD_PROJECT') == 'test-gcs-env'
            
            gcs_emulator._unset_env_vars()
            assert os.environ.get('STORAGE_EMULATOR_HOST') is None
            
        finally:
            # 環境変数を元に戻す
            if original_firestore_host:
                os.environ['FIRESTORE_EMULATOR_HOST'] = original_firestore_host
            if original_storage_host:
                os.environ['STORAGE_EMULATOR_HOST'] = original_storage_host


if __name__ == '__main__':
    # 基本的な動作確認
    print("🔧 エミュレータ利用可能性チェック開始...")
    
    # gcloudの確認
    gcloud_available = shutil.which('gcloud') is not None
    print(f"✓ gcloud: {'利用可能' if gcloud_available else '❌ 利用不可'}")
    
    # Dockerの確認
    docker_available = shutil.which('docker') is not None
    print(f"✓ Docker: {'利用可能' if docker_available else '❌ 利用不可'}")
    
    if docker_available:
        try:
            result = subprocess.run(['docker', 'info'], capture_output=True, timeout=5)
            docker_running = result.returncode == 0
            print(f"✓ Docker daemon: {'動作中' if docker_running else '❌ 停止中'}")
        except:
            print("✓ Docker daemon: ❌ 確認失敗")
    
    print("\n推奨事項:")
    if not gcloud_available:
        print("- Google Cloud SDKをインストールしてください")
    if not docker_available:
        print("- Dockerをインストールしてください（GCSエミュレータ用）")
    
    print("\n✅ エミュレータ利用可能性チェック完了")
