import subprocess
import time
import os
import shutil
import requests
from contextlib import contextmanager
import logging
import uuid # For unique container names
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
            # Basic check, specific emulators might need more robust checks
            response = requests.get(f"http://{self.host}:{self.port}", timeout=1)
            return response.status_code == 200 # Or other relevant status
        except requests.ConnectionError:
            return False
        except Exception as e:
            logger.warning(f"Error checking emulator status: {e}")
            return False

class FirestoreEmulator(EmulatorManager):
    def __init__(self, host='localhost', port=8081, project_id='test-project', executable_path='gcloud', data_dir: Optional[str] = None):
        super().__init__(host, port, project_id)
        self.executable_path = executable_path
        self.data_dir = data_dir
        if self.data_dir:
            # Ensure data_dir is absolute as gcloud might have CWD issues
            self.data_dir = os.path.abspath(self.data_dir)
            os.makedirs(self.data_dir, exist_ok=True)
            logger.info(f"Firestore emulator data will be stored in: {self.data_dir}")
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
        if self.data_dir:
            command.append(f"--data-dir={self.data_dir}")
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(5) # Give emulator time to start
        if self.process.poll() is not None: # Process terminated unexpectedly
            stdout, stderr = self.process.communicate()
            logger.error(f"Firestore emulator failed to start. Return code: {self.process.returncode}")
            logger.error(f"Stdout: {stdout.decode()}")
            logger.error(f"Stderr: {stderr.decode()}")
            raise RuntimeError("Failed to start Firestore emulator.")
        self._set_env_vars()
        if self.data_dir:
            logger.info(f"Firestore emulator started. Data directory: {self.data_dir}")
        else:
            logger.info("Firestore emulator started (in-memory).")

    def clear_data(self):
        logger.info("Clearing Firestore emulator data...")
        try:
            # Firestore emulator data can be cleared by making a DELETE request
            # to the /clear endpoint (this needs to be enabled or might be default)
            # Or, more reliably, by stopping and restarting with a fresh instance if no specific clear endpoint.
            # For simplicity, we assume client-side data reset or restart.
            # A more robust way: http://localhost:8081/emulator/v1/projects/test-project/databases/(default)/documents
            # However, this requires knowing the project ID.
            # The Firebase CLI or gcloud emulator has specific commands to clear data,
            # but this class doesn't assume those CLIs are used for data clearing *during* runtime.
            # For testing, typically you'd re-initialize the client or restart the emulator.
            # Here, we'll try a common (but not always available) clear endpoint.
            # A more direct way is to use the admin API if available and configured.
            if self.data_dir and os.path.exists(self.data_dir):
                logger.info(f"Attempting to clear Firestore data from data directory: {self.data_dir}")
                # This is a destructive operation. For Firestore, the data is usually within a subdirectory or specific files.
                # The gcloud emulator stores data in a 'persistence.db' file or similar within the data_dir.
                # For simplicity, we might remove the known file or the entire directory if that's acceptable.
                # However, simply deleting the directory might be too aggressive if other things are stored there.
                # For now, we'll log that manual removal of contents of data_dir is needed for full clear if using --data-dir.
                logger.warning(f"Persistent Firestore data at {self.data_dir} is not automatically cleared by this method. Manual removal may be needed.")
            # This needs to be a DELETE request to each document, or a special endpoint.
            logger.info(f"Data clearing for Firestore emulator (especially persistent) typically requires more specific actions or manual intervention if a data_dir is used.")
            # Example for clearing (requires project_id and may need auth/specific setup):
            # requests.delete(f"http://{self.emulator_host_env}/emulator/v1/projects/{self.project_id}/databases/(default)/documents")
        except Exception as e:
            logger.error(f"Failed to clear Firestore data: {e}")

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
                 port=9000, # Default port for fake-gcs-server
                 project_id='test-project',
                 executable_path='fake-gcs-server', # ローカル実行時の実行ファイルパス (現在は未使用)
                 use_docker=True, # Dockerを使用するかどうかのフラグ (現在は常にTrueとして動作)
                 docker_image='fsouza/fake-gcs-server:latest', # 使用するDockerイメージ
                 host_data_path="/root/onedrive/working/googlerun-react-chatsystem", # データ保存先のホストパス
                 container_name_prefix='fake-gcs-pytest-'):

        super().__init__(host, port, project_id)
        logger.info(f"GCSEmulator __init__: Initial host_data_path arg: {host_data_path}")
        self.use_docker = use_docker # Though it's always True now
        self.docker_image = docker_image
        self.host_data_path = os.path.abspath(host_data_path)
        self.container_data_path = "/data" # Standard mount point inside the container
        self.container_name = f"{container_name_prefix}{uuid.uuid4().hex[:8]}" # Unique container name

        # ホストデータディレクトリが存在しない場合は作成
        logger.info(f"GCSEmulator instance configured with host_data_path: {self.host_data_path}")
        if not os.path.exists(self.host_data_path):
            os.makedirs(self.host_data_path, exist_ok=True)
            logger.info(f"Created host data directory: {self.host_data_path}")

        self.emulator_host_env = f"http://{self.host}:{self.port}" # fake-gcs-server uses full URL

    def start(self):
        if self.is_running(): # is_running() will now use the corrected health check
            logger.info(f"GCS emulator already running on {self.emulator_host_env}")
            self._set_env_vars()
            return
        logger.info(f"GCSEmulator.start() called. Using host_data_path: {self.host_data_path} for volume mount.")

        # Always use Docker as local binary mode is removed
        if not shutil.which("docker"):
            raise RuntimeError("Docker client not found. Please install Docker.")
        logger.info(f"Starting GCS emulator using Docker image {self.docker_image} on port {self.port}...")
        logger.info(f"Host data directory (for GCS data): {self.host_data_path} will be mounted to {self.container_data_path} in container {self.container_name}")

        # Ensure previous container with the same name is removed (if any, though unlikely with UUID)
        try:
            # 古いコンテナが残っていれば削除
            subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True, check=False, text=True)
        except FileNotFoundError:
            logger.error("Docker command not found. Make sure Docker is installed and in PATH.")
            raise

        # Docker run command
        command = [
            "docker", "run",
            "-d", # デタッチモードで実行
            "--name", self.container_name,
            "--rm", # Automatically remove the container when it exits
            "-p", f"{self.port}:{self.port}", # ポートマッピング
            "-v", f"{self.host_data_path}:{self.container_data_path}", # ホストのデータパスをコンテナの/dataにマウント
            self.docker_image,
            "-scheme", "http", # fake-gcs-server specific args
            "-host", "0.0.0.0", # Listen on all interfaces inside the container
            "-port", str(self.port),
            "-data", self.container_data_path,
            "-public-host", self.host, # How clients should reach it (e.g., localhost)
        ]

        logger.info(f"Executing Docker command: {' '.join(command)}")
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)

        if process.returncode != 0:
            logger.error(f"Docker run command failed with exit code {process.returncode}")
            logger.error(f"Docker run STDOUT: {process.stdout.strip()}")
            logger.error(f"Docker run STDERR: {process.stderr.strip()}")
            raise RuntimeError(f"Docker run command failed. STDERR: {process.stderr.strip()}")
        else:
            logger.info(f"Docker run command successful. Container ID (from stdout): {process.stdout.strip()}")

        time.sleep(5) # コンテナ起動のための待機時間

        # Wait a bit more and then check if it's actually listening
        time.sleep(2)
        if not self.is_running(): # This will use the corrected health check
            # Fetch Docker logs for more insight
            logs_command = ["docker", "logs", self.container_name]
            try:
                logs_result = subprocess.run(logs_command, capture_output=True, text=True, timeout=5)
                logger.error(f"Docker container {self.container_name} logs:\nSTDOUT:\n{logs_result.stdout}\nSTDERR:\n{logs_result.stderr}")
            except Exception as e:
                logger.error(f"Failed to get logs for Docker container {self.container_name}: {e}")
            
            # Attempt to stop the container as --rm should remove it on exit, but it might not have exited cleanly.
            subprocess.run(["docker", "stop", self.container_name], capture_output=True, check=False, text=True)
            raise RuntimeError(f"GCS emulator failed to become ready on {self.emulator_host_env} after starting.")

        self._set_env_vars()
        logger.info(f"GCS emulator started and accessible at {self.emulator_host_env}. Data dir: container:{self.container_data_path} (host:{self.host_data_path})")


    def stop(self):
        if hasattr(self, 'container_name') and self.container_name:
            logger.info(f"Stopping GCS emulator Docker container {self.container_name}...")
            try:
                # `docker run --rm` がコンテナ終了時に自動削除するが、明示的な停止も行う
                subprocess.run(["docker", "stop", self.container_name], capture_output=True, timeout=10, check=False, text=True)
                logger.info(f"GCS emulator Docker container {self.container_name} stopped.")
            except FileNotFoundError:
                logger.error("Docker command not found. Cannot stop container.")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout trying to stop container {self.container_name}. It might have already stopped or may need manual removal.")
            except Exception as e:
                logger.error(f"Error stopping/removing Docker container {self.container_name}: {e}")
        self._unset_env_vars()

    def clear_data(self):
        logger.info(f"GCSEmulator.clear_data() called. Host data path to be cleared: {self.host_data_path}")
        logger.info(f"Attempting to clear GCS emulator data in host directory: {self.host_data_path}")
        if os.path.exists(self.host_data_path):
            for item_name in os.listdir(self.host_data_path):
                item_path = os.path.join(self.host_data_path, item_name)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    logger.error(f"Failed to delete {item_path} during data clear: {e}")
            logger.info(f"GCS emulator data cleared from host directory: {self.host_data_path}")
        else:
            logger.info(f"Host data directory {self.host_data_path} does not exist, nothing to clear.")

    def _set_env_vars(self):
        os.environ['STORAGE_EMULATOR_HOST'] = self.emulator_host_env
        os.environ['GCS_EMULATOR_HOST'] = self.emulator_host_env # Some libraries might look for this
        os.environ['GOOGLE_CLOUD_PROJECT'] = self.project_id # Good practice for client libraries
        logger.info(f"Set STORAGE_EMULATOR_HOST to {self.emulator_host_env}")
        logger.info(f"Set GCS_EMULATOR_HOST to {self.emulator_host_env}")
        logger.info(f"Set GOOGLE_CLOUD_PROJECT to {self.project_id}")

    def _unset_env_vars(self):
        for var in ['STORAGE_EMULATOR_HOST', 'GCS_EMULATOR_HOST', 'GOOGLE_CLOUD_PROJECT']:
            if var in os.environ:
                del os.environ[var]
                logger.info(f"Unset {var}")

    def is_running(self):
        # Check if container is running first
        if not hasattr(self, 'container_name') or not self.container_name:
            return False # Should not happen if start was called
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.container_name}"],
                capture_output=True, text=True, check=True
            )
            if not result.stdout.strip(): # Container not found among running containers
                logger.debug(f"GCS emulator container {self.container_name} not found in 'docker ps'.")
                return False
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Failed to check Docker status for {self.container_name}: {e}")
            return False # Docker command failed or container not found

        # Now check HTTP health endpoint
        health_check_url = self.emulator_host_env + "/_internal/healthcheck"
        try:
            response = requests.get(health_check_url, timeout=2)
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"GCS emulator health check at {health_check_url} returned status {response.status_code}.")
                return False
        except requests.ConnectionError:
            logger.warning(f"GCS emulator health check: Connection error at {health_check_url}.")
            return False
        except Exception as e:
            logger.warning(f"Error checking GCS emulator status at {health_check_url}: {e}")
            return False

@contextmanager
def firestore_emulator_context(host='localhost', port=8081, project_id='test-project', executable_path='gcloud', data_dir: Optional[str] = None):
    emulator = FirestoreEmulator(host, port, project_id, executable_path, data_dir=data_dir)
    try:
        emulator.start()
        # Firestore client should be initialized by the caller using os.environ['FIRESTORE_EMULATOR_HOST']
        yield emulator # Yield the emulator instance itself, not a client
    finally:
        emulator.stop()

@contextmanager
def gcs_emulator_context(host='localhost', port=9000, project_id='test-project',
                         use_docker=True, # Remains for compatibility, but effectively always True
                         docker_image='fsouza/fake-gcs-server:latest',
                         host_data_path=os.path.join(os.path.dirname(__file__), 'data')): # Default path if not overridden
    emulator = GCSEmulator(host=host, port=port, project_id=project_id,
                           use_docker=True, docker_image=docker_image, host_data_path=host_data_path)
    try:
        emulator.start()
        # GCS client should be initialized by the caller using os.environ['STORAGE_EMULATOR_HOST']
        yield emulator # Yield the emulator instance itself, not a client
    finally:
        emulator.stop()

if __name__ == '__main__':
    # Example usage:

    # Test Firestore Emulator
    try:
        with firestore_emulator_context(port=8091, project_id="fs-test") as fs_emulator:
            logger.info(f"Firestore Emulator Host for test: {os.getenv('FIRESTORE_EMULATOR_HOST')}")
            # Example of client usage (requires google-cloud-firestore)
            try:
                from google.cloud import firestore
                db = firestore.Client(project=fs_emulator.project_id) # Use emulator's project_id
                doc_ref = db.collection('users').document('alovelace')
                doc_ref.set({'first': 'Ada', 'last': 'Lovelace', 'born': 1815})
                doc = doc_ref.get()
                logger.info(f"Firestore Doc: {doc.to_dict()}")
                doc_ref.delete() # Clean up
            except ImportError:
                logger.warning("google-cloud-firestore library not installed. Skipping Firestore interaction example.")
            except Exception as e:
                logger.error(f"Error interacting with Firestore emulator: {e}")
    except RuntimeError as e:
        logger.error(f"Failed to run Firestore emulator: {e}")

    logger.info("\n" + "="*30 + "\n")

    # Test GCS Emulator (Docker)
    # Ensure Docker is running for this part
    if shutil.which("docker"):
        # Define a specific data path for this test relative to this script
        current_script_dir = os.path.dirname(__file__)
        gcs_test_data_path = os.path.join(current_script_dir, 'gcs_data_docker_test')
        os.makedirs(gcs_test_data_path, exist_ok=True)

        try:
            with gcs_emulator_context(port=9092, project_id="gcs-test", host_data_path=gcs_test_data_path) as gcs_emulator:
                logger.info(f"GCS Emulator (Docker) Host for test: {os.getenv('STORAGE_EMULATOR_HOST')}")
                # Example of client usage (requires google-cloud-storage)
                try:
                    from google.cloud import storage
                    storage_client = storage.Client(project=gcs_emulator.project_id) # Use emulator's project_id
                    bucket_name = f"{gcs_emulator.project_id}-my-bucket-docker"
                    bucket = storage_client.create_bucket(bucket_name)
                    logger.info(f"Bucket {bucket.name} created (Docker).")
                    blob = bucket.blob("test_docker.txt")
                    blob.upload_from_string("Hello from Docker GCS emulator!")
                    logger.info(f"Blob {blob.name} uploaded (Docker).")
                    logger.info(f"Blob content: {blob.download_as_text()} (Docker).")
                    blob.delete()
                    bucket.delete()
                    logger.info("Cleaned up bucket and blob (Docker).")
                    gcs_emulator.clear_data() # Test clearing data
                except ImportError:
                    logger.warning("google-cloud-storage library not installed. Skipping GCS interaction example.")
                except Exception as e:
                    logger.error(f"Error interacting with GCS emulator (Docker): {e}")
        except RuntimeError as e:
            logger.error(f"Failed to run GCS emulator (Docker): {e}")
        finally:
            # Clean up the test data directory
            if os.path.exists(gcs_test_data_path):
                shutil.rmtree(gcs_test_data_path)
    else:
        logger.warning("Docker is not installed or not in PATH. Skipping GCS Docker emulator example.")