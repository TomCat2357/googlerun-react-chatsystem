import subprocess
import time
import os
import shutil
import requests
from contextlib import contextmanager
import logging
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmulatorManager:
    def __init__(self, host='localhost', port=8080, project_id='test-project'):
        self.host = host
        self.port = port
        self.project_id = project_id
        self.process = None
        self.emulator_host_env = f"{self.host}:{self.port}"

    def start(self):
        raise NotImplementedError

    def stop(self):
        if self.process:
            logger.info(f"Stopping {self.__class__.__name__} on port {self.port}...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"{self.__class__.__name__} did not terminate gracefully, killing...")
                self.process.kill()
            self.process = None
            logger.info(f"{self.__class__.__name__} stopped.")
        self._unset_env_vars()

    def clear_data(self):
        raise NotImplementedError

    def _set_env_vars(self):
        raise NotImplementedError

    def _unset_env_vars(self):
        raise NotImplementedError

    def is_running(self):
        try:
            response = requests.get(f"http://{self.host}:{self.port}", timeout=1)
            return response.status_code == 200
        except requests.ConnectionError:
            return False
        except Exception as e:
            logger.warning(f"Error checking emulator status: {e}")
            return False

class FirestoreEmulator(EmulatorManager):
    def __init__(self, host='localhost', port=8081, project_id='test-project', executable_path='gcloud', data_dir=None):
        super().__init__(host, port, project_id)
        self.executable_path = executable_path
        # data_dirは使用しない（常にin-memory）
        self.data_dir = None
        self.emulator_host_env = f"{self.host}:{self.port}"

    def start(self):
        if self.is_running():
            logger.info(f"Firestore emulator already running on {self.emulator_host_env}")
            self._set_env_vars()
            return

        logger.info(f"Starting Firestore emulator on port {self.port} for project {self.project_id}...")
        command = [
            self.executable_path,
            "beta",
            "emulators",
            "firestore",
            "start",
            f"--host-port={self.emulator_host_env}",
            f"--project={self.project_id}",
        ]
        
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(5)
        
        if self.process.poll() is not None:
            stdout, stderr = self.process.communicate()
            logger.error(f"Firestore emulator failed to start. Return code: {self.process.returncode}")
            logger.error(f"Stderr: {stderr.decode()}")
            raise RuntimeError("Failed to start Firestore emulator.")
        
        self._set_env_vars()
        logger.info("Firestore emulator started (in-memory)")

    def clear_data(self):
        """データクリア（REST APIまたは再起動）"""
        logger.info("Clearing Firestore emulator data...")
        if not self.is_running():
            logger.warning("Firestore emulator is not running")
            return
        
        # REST APIでクリア
        try:
            clear_url = f"http://{self.emulator_host_env}/emulator/v1/projects/{self.project_id}/databases/(default)/documents"
            response = requests.delete(clear_url, timeout=10)
            if response.status_code in [200, 204]:
                logger.info("Successfully cleared Firestore emulator data")
                return
        except Exception as e:
            logger.warning(f"REST API clear failed: {e}")
        
        # 再起動でクリア
        logger.info("Restarting Firestore emulator to clear data")
        self.stop()
        time.sleep(1)
        self.start()

    def _set_env_vars(self):
        os.environ['FIRESTORE_EMULATOR_HOST'] = self.emulator_host_env
        logger.info(f"Set FIRESTORE_EMULATOR_HOST to {self.emulator_host_env}")

    def _unset_env_vars(self):
        if 'FIRESTORE_EMULATOR_HOST' in os.environ:
            del os.environ['FIRESTORE_EMULATOR_HOST']
            logger.info("Unset FIRESTORE_EMULATOR_HOST")

class GCSEmulator(EmulatorManager):
    def __init__(self,
                 host='localhost',
                 port=9000,
                 project_id='test-project',
                 docker_image='fsouza/fake-gcs-server:latest',
                 container_name_prefix='fake-gcs-pytest-'):

        super().__init__(host, port, project_id)
        self.docker_image = docker_image
        self.container_name = f"{container_name_prefix}{project_id}-{str(port)}"
        self.emulator_host_env = f"http://{self.host}:{self.port}"

    def start(self):
        if self.is_running():
            logger.info(f"GCS emulator already running on {self.emulator_host_env}")
            self._set_env_vars()
            return

        logger.info(f"Starting GCS emulator using Docker image {self.docker_image} on port {self.port}...")

        # Always use Docker
        if not shutil.which("docker"):
            raise RuntimeError("Docker client not found. Please install Docker.")

        # 既存コンテナを停止・削除
        self._stop_existing_containers()

        # Docker run command (データ永続化なし、コンテナ削除時にデータも削除)
        command = [
            "docker", "run",
            "-d", "--rm",  # --rmでコンテナ停止時に自動削除
            "--name", self.container_name,
            "-p", f"{self.port}:{self.port}",
            self.docker_image,
            "-scheme", "http",
            "-host", "0.0.0.0",
            "-port", str(self.port),
            "-public-host", self.host,
        ]

        logger.info(f"Executing Docker command: {' '.join(command)}")
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)

        if process.returncode != 0:
            logger.error(f"Docker run failed: {process.stderr.strip()}")
            raise RuntimeError(f"Docker run command failed. STDERR: {process.stderr.strip()}")

        logger.info(f"Docker run successful. Container ID: {process.stdout.strip()}")

        # コンテナ起動の待機
        time.sleep(3)

        # ヘルスチェック
        if not self.is_running():
            logs_command = ["docker", "logs", self.container_name]
            try:
                logs_result = subprocess.run(logs_command, capture_output=True, text=True, timeout=5)
                logger.error(f"Container logs:\nSTDOUT:\n{logs_result.stdout}\nSTDERR:\n{logs_result.stderr}")
            except Exception as e:
                logger.error(f"Failed to get logs: {e}")
            
            subprocess.run(["docker", "stop", self.container_name], capture_output=True, check=False, text=True)
            raise RuntimeError(f"GCS emulator failed to become ready on {self.emulator_host_env}")

        self._set_env_vars()
        logger.info(f"GCS emulator started at {self.emulator_host_env}")

    def stop(self):
        if hasattr(self, 'container_name') and self.container_name:
            logger.info(f"Stopping GCS emulator container {self.container_name}...")
            try:
                subprocess.run(["docker", "stop", self.container_name], capture_output=True, timeout=10, check=False, text=True)
                logger.info(f"GCS emulator container {self.container_name} stopped")
            except Exception as e:
                logger.error(f"Error stopping container: {e}")
        self._unset_env_vars()

    def clear_data(self):
        """データクリア（コンテナ再起動で実現）"""
        logger.info("Clearing GCS emulator data by restarting container")
        was_running = self.is_running()
        if was_running:
            self.stop()
            time.sleep(1)
            self.start()
            logger.info("GCS emulator restarted with cleared data")

    def _set_env_vars(self):
        os.environ['STORAGE_EMULATOR_HOST'] = self.emulator_host_env
        os.environ['GCS_EMULATOR_HOST'] = self.emulator_host_env
        os.environ['GOOGLE_CLOUD_PROJECT'] = self.project_id
        logger.info(f"Set STORAGE_EMULATOR_HOST to {self.emulator_host_env}")

    def _unset_env_vars(self):
        for var in ['STORAGE_EMULATOR_HOST', 'GCS_EMULATOR_HOST', 'GOOGLE_CLOUD_PROJECT']:
            if var in os.environ:
                del os.environ[var]
                logger.info(f"Unset {var}")

    def _stop_existing_containers(self):
        """既存コンテナの停止・削除"""
        try:
            # 同名コンテナを停止・削除
            result = subprocess.run(
                ["docker", "ps", "-a", "-q", "--filter", f"name={self.container_name}"],
                capture_output=True, text=True, check=False
            )
            
            if result.stdout.strip():
                logger.info(f"Stopping and removing existing container: {self.container_name}")
                subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True, check=False, text=True)
            
            # ポート使用中のコンテナを停止
            result = subprocess.run(
                ["docker", "ps", "-q", "--filter", f"publish={self.port}"],
                capture_output=True, text=True, check=False
            )
            
            if result.stdout.strip():
                container_ids = result.stdout.strip().split('\n')
                for container_id in container_ids:
                    logger.info(f"Stopping container using port {self.port}: {container_id}")
                    subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, check=False, text=True)
            
            time.sleep(1)
            
        except Exception as e:
            logger.warning(f"Error during container cleanup: {e}")

    def is_running(self):
        # コンテナ確認
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.container_name}"],
                capture_output=True, text=True, check=True
            )
            if not result.stdout.strip():
                return False
        except Exception:
            return False

        # HTTPヘルスチェック
        try:
            health_url = self.emulator_host_env + "/_internal/healthcheck"
            response = requests.get(health_url, timeout=2)
            return response.status_code == 200
        except Exception:
            return False

@contextmanager
def firestore_emulator_context(host='localhost', port=8081, project_id='test-project', executable_path='gcloud', data_dir: Optional[str] = None):
    emulator = FirestoreEmulator(host, port, project_id, executable_path, data_dir=data_dir)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

@contextmanager
def gcs_emulator_context(host='localhost', port=9000, project_id='test-project',
                         use_docker=True,
                         docker_image='fsouza/fake-gcs-server:latest',
                         host_data_path=None):
    
    # host_data_pathは無視（データ永続化しない）
    if host_data_path is not None:
        logger.info("Note: host_data_path is ignored - data will not persist")
    
    emulator = GCSEmulator(host=host, port=port, project_id=project_id, docker_image=docker_image)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

if __name__ == '__main__':
    # Simple example usage
    logger.info("Testing GCP emulators...")
    
    # Test Firestore
    try:
        with firestore_emulator_context(port=8091, project_id="fs-test") as fs_emulator:
            logger.info("Firestore emulator test passed")
    except Exception as e:
        logger.error(f"Firestore test failed: {e}")

    # Test GCS  
    try:
        with gcs_emulator_context(port=9092, project_id="gcs-test") as gcs_emulator:
            logger.info("GCS emulator test passed")
    except Exception as e:
        logger.error(f"GCS test failed: {e}")
