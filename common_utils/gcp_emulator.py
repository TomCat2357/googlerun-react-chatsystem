import subprocess
import time
import os
import shutil
import requests
from contextlib import contextmanager
import logging
import uuid # For unique container names

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
    def __init__(self, host='localhost', port=8081, project_id='test-project', executable_path='gcloud'):
        super().__init__(host, port, project_id)
        self.executable_path = executable_path
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
        time.sleep(5) # Give emulator time to start
        if self.process.poll() is not None: # Process terminated unexpectedly
            stdout, stderr = self.process.communicate()
            logger.error(f"Firestore emulator failed to start. Return code: {self.process.returncode}")
            logger.error(f"Stdout: {stdout.decode()}")
            logger.error(f"Stderr: {stderr.decode()}")
            raise RuntimeError("Failed to start Firestore emulator.")
        self._set_env_vars()
        logger.info("Firestore emulator started.")

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
            clear_url = f"http://{self.host}:{self.port}/emulator/v1/projects/{self.project_id}/databases/(default)/documents"
            # This needs to be a DELETE request to each document, or a special endpoint.
            # The simplest way for many tests is to rely on a fresh emulator instance.
            # For now, we'll just log it. Proper clearing depends on specific emulator features.
            logger.info(f"Data clearing for Firestore emulator is typically handled by restarting or specific client actions.")
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
                 project_id='test-project', # [cite: 164]
                 executable_path='fake-gcs-server', # ローカル実行時の実行ファイルパス
                 use_docker=True, # Dockerを使用するかどうかのフラグ
                 docker_image='fsouza/fake-gcs-server:latest', # 使用するDockerイメージ
                 # データ保存先のホストパス。プロジェクトルートからの相対パスを想定。
                 # (project_root)/common_utils/data に対応。
                 host_data_path=os.path.join(os.path.dirname(__file__), 'data'),
                 container_name_prefix='fake-gcs-pytest-'):

        super().__init__(host, port, project_id) # [cite: 165]
        # self.executable_path = executable_path # Local binary mode removed
        self.use_docker = use_docker
        self.docker_image = docker_image
        # Ensure host_data_path is absolute
        self.host_data_path = os.path.abspath(host_data_path)
        self.container_data_path = "/data" # Standard mount point inside the container
        self.container_name = f"{container_name_prefix}{uuid.uuid4().hex[:8]}" # Unique container name

        # ホストデータディレクトリが存在しない場合は作成
        if not os.path.exists(self.host_data_path):
            os.makedirs(self.host_data_path, exist_ok=True)
            logger.info(f"Created host data directory: {self.host_data_path}")

        self.emulator_host_env = f"http://{self.host}:{self.port}" # fake-gcs-server uses full URL

    def start(self):
        if self.is_running():
            logger.info(f"GCS emulator already running on {self.emulator_host_env}")
            self._set_env_vars()
            return

        # Always use Docker as local binary mode is removed
        if not shutil.which("docker"):
            raise RuntimeError("Docker client not found. Please install Docker.") # [cite: 168]
            logger.info(f"Starting GCS emulator using Docker image {self.docker_image} on port {self.port}...")
            logger.info(f"Host data directory (for GCS data): {self.host_data_path} will be mounted to {self.container_data_path} in container {self.container_name}")

            # Ensure previous container with the same name is removed (if any, though unlikely with UUID)
            try:
                # 古いコンテナが残っていれば削除
                subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True, check=False) # [cite: 169]
            except FileNotFoundError:
                logger.error("Docker command not found. Make sure Docker is installed and in PATH.")
                raise

            # Docker run command
            # イメージが存在しない場合は自動的にpullされる
            command = [
                "docker", "run",
                "-d", # デタッチモードで実行
                "--name", self.container_name,
                "--rm", # Automatically remove the container when it exits
                "-p", f"{self.port}:{self.port}", # ポートマッピング
                # ホストのデータパスをコンテナの/dataにマウント
                "-v", f"{self.host_data_path}:{self.container_data_path}",
                self.docker_image,
                "-scheme", "http", # fake-gcs-server specific args
                "-host", "0.0.0.0", # Listen on all interfaces inside the container
                "-port", str(self.port),
                "-data", self.container_data_path,
                "-public-host", self.host, # How clients should reach it (e.g., localhost)
            ] # [cite: 170, 171, 172]
            # For Docker detached mode, Popen returns immediately. We don't store this process.
            subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) # [cite: 173]
            time.sleep(3) # Give Docker container time to start

            # Check if docker run was successful (process still running means CLI call finished)
            # We need to check container logs or `docker ps` for actual status
            # For simplicity, we assume Popen was for the `docker run -d` command itself.
            # A more robust check would be `docker ps -f name=self.container_name`
            # or check `self.is_running()` which pings the http endpoint. # [cite: 174]
        # else: # Use local binary - REMOVED
            # logger.info(f"Starting GCS emulator (local binary: {self.executable_path}) on port {self.port}...")
            # logger.info(f"Data for GCS will be stored in: {self.host_data_path}") # For local binary, data path is specified differently
            # command = [
            #     self.executable_path,
            #     "-scheme", "http",
            #     "-host", self.host, # [cite: 176]
            #     "-port", str(self.port),
            #     "-data", self.host_data_path, # For local binary, it directly uses this path
            #     "-public-host", self.host, # [cite: 176]
            # ]
            # self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) # [cite: 177]
            # time.sleep(2) # Give emulator time to start

        # Common checks after attempting to start
        # if self.process and self.process.poll() is not None and not self.use_docker: # Check for local binary failure - REMOVED
            # stdout, stderr = self.process.communicate()
            # logger.error(f"GCS emulator (local binary) failed to start. Return code: {self.process.returncode}") # [cite: 178]
            # logger.error(f"Stdout: {stdout.decode(errors='ignore')}") # [cite: 178]
            # logger.error(f"Stderr: {stderr.decode(errors='ignore')}") # [cite: 178]
            # raise RuntimeError("Failed to start GCS emulator (local binary).")

        # Wait a bit more and then check if it's actually listening
        time.sleep(2)
        if not self.is_running():
            # Always use_docker now
            # if self.use_docker:
                # Fetch Docker logs for more insight
            logs_command = ["docker", "logs", self.container_name] # [cite: 179]
            try:
                logs_result = subprocess.run(logs_command, capture_output=True, text=True, timeout=5)
                logger.error(f"Docker container {self.container_name} logs:\nSTDOUT:\n{logs_result.stdout}\nSTDERR:\n{logs_result.stderr}") # [cite: 180]
            except Exception as e:
                logger.error(f"Failed to get logs for Docker container {self.container_name}: {e}")
                
            # Attempt to stop/remove the potentially failed container if not using --rm (though we are)
            subprocess.run(["docker", "stop", self.container_name], capture_output=True, check=False) # [cite: 181]

            raise RuntimeError(f"GCS emulator failed to become ready on {self.emulator_host_env} after starting.")

        self._set_env_vars()
        logger.info(f"GCS emulator started and accessible at {self.emulator_host_env}. Data dir: container:{self.container_data_path} (host:{self.host_data_path})") # [cite: 182]


    def stop(self):
        # Always use_docker now
        if hasattr(self, 'container_name') and self.container_name:
                logger.info(f"Stopping GCS emulator Docker container {self.container_name}...")
                try:
                    # `docker run --rm` がコンテナ終了時に自動削除するが、明示的な停止も行う
                    subprocess.run(["docker", "stop", self.container_name], capture_output=True, timeout=10, check=False) # [cite: 183]
                    logger.info(f"GCS emulator Docker container {self.container_name} stopped.")
                except FileNotFoundError:
                    logger.error("Docker command not found. Cannot stop container.")
                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout trying to stop container {self.container_name}. It might have already stopped or may need manual removal.") # [cite: 184]
                except Exception as e:
                    logger.error(f"Error stopping/removing Docker container {self.container_name}: {e}")
                # self.process = None # Popen object was for `docker run`, not the daemon # [cite: 185]
        # else: # Local binary - REMOVED
            # if self.process:
                # super().stop() # Call EmulatorManager's stop for local process

        self._unset_env_vars()

    def clear_data(self):
        logger.info(f"Attempting to clear GCS emulator data in host directory (for GCS): {self.host_data_path}")
        # This method clears the *host* directory, which is mounted into the Docker container
        # or used directly by the local binary.
        if os.path.exists(self.host_data_path):
            for item_name in os.listdir(self.host_data_path):
                item_path = os.path.join(self.host_data_path, item_name)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path) # [cite: 188]
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    logger.error(f"Failed to delete {item_path} during data clear: {e}")
            logger.info(f"GCS emulator data cleared from host directory: {self.host_data_path}")
        else:
            logger.info(f"Host data directory {self.host_data_path} does not exist, nothing to clear.")


    def _set_env_vars(self):
        os.environ['STORAGE_EMULATOR_HOST'] = self.emulator_host_env
        # Some libraries might also look for GCS_EMULATOR_HOST or GOOGLE_CLOUD_PROJECT
        os.environ['GCS_EMULATOR_HOST'] = self.emulator_host_env
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
        # fake-gcs-server serves a / (root) endpoint that returns 200 OK by default
        # or specific health check endpoint if available. # [cite: 191]
        # For fake-gcs-server, the base URL itself should work. # [cite: 192]
        # Always use_docker now
        # Check if container is running and then if service is responsive
        if not hasattr(self, 'container_name') or not self.container_name:
            return False
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.container_name}"],
                capture_output=True, text=True, check=True
            )
            if not result.stdout.strip(): # コンテナが見つからない
                return False
        except (subprocess.CalledProcessError, FileNotFoundError): # [cite: 194]
            return False # Dockerコマンド失敗またはコンテナが見つからない

        # Now check HTTP endpoint for both Docker and local binary
        try:
            # The public host for fake-gcs-server might not respond on /
            # but the API endpoints like /storage/v1/b should exist.
            # A simple GET to the base URL should be fine.
            response = requests.get(self.emulator_host_env + "/", timeout=2) # Added slash
            # fake-gcs-server usually returns 200 on its root.
            # Or, more specific: try listing buckets (requires no buckets initially)
            # response = requests.get(self.emulator_host_env + "/storage/v1/b?project=" + self.project_id, timeout=1)
            return response.status_code == 200
        except requests.ConnectionError:
            return False
        except Exception as e:
            logger.warning(f"Error checking GCS emulator status at {self.emulator_host_env}: {e}")
            return False


@contextmanager
def firestore_emulator_context(host='localhost', port=8081, project_id='test-project', executable_path='gcloud'):
    emulator = FirestoreEmulator(host, port, project_id, executable_path)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

@contextmanager
def gcs_emulator_context(host='localhost', port=9000, project_id='test-project',
                         # executable_path='fake-gcs-server', # Removed
                         use_docker=True, # Remains for compatibility, but effectively always True
                         docker_image='fsouza/fake-gcs-server:latest', # [cite: 199]
                         host_data_path=os.path.join(os.path.dirname(__file__), 'data')):
    emulator = GCSEmulator(host, port, project_id, use_docker=True, docker_image=docker_image, host_data_path=host_data_path)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

if __name__ == '__main__':
    # Example usage:

    # Test Firestore Emulator
    try:
        with firestore_emulator_context(port=8091) as fs_emulator:
            logger.info(f"Firestore Emulator Host: {os.getenv('FIRESTORE_EMULATOR_HOST')}")
            # Here you would run tests that use Firestore
            from google.cloud import firestore
            try:
                db = firestore.Client(project=fs_emulator.project_id)
                doc_ref = db.collection('users').document('alovelace')
                doc_ref.set({'first': 'Ada', 'last': 'Lovelace', 'born': 1815})
                doc = doc_ref.get()
                logger.info(f"Firestore Doc: {doc.to_dict()}")
                doc_ref.delete() # Clean up
            except Exception as e:
                logger.error(f"Error interacting with Firestore emulator: {e}")
    except RuntimeError as e:
        logger.error(f"Failed to run Firestore emulator: {e}")
    except ImportError:
        logger.warning("google-cloud-firestore library not installed. Skipping Firestore example.")


    logger.info("\n" + "="*30 + "\n")

    # Test GCS Emulator (Local Binary) - REMOVED
    # try:
        # with gcs_emulator_context(port=9091, use_docker=False, host_data_path=os.path.join(os.path.dirname(__file__), 'gcs_data_local')) as gcs_emulator_local:
            # logger.info(f"GCS Emulator (Local) Host: {os.getenv('STORAGE_EMULATOR_HOST')}")
            # from google.cloud import storage
            # try:
                # storage_client = storage.Client(project=gcs_emulator_local.project_id) # [cite: 204]
                # bucket_name = f"{gcs_emulator_local.project_id}-my-bucket-local" # [cite: 204]
                # bucket = storage_client.create_bucket(bucket_name) # [cite: 204]
                # logger.info(f"Bucket {bucket.name} created (local).") # [cite: 204]
                # blob = bucket.blob("test_local.txt") # [cite: 204]
                # blob.upload_from_string("Hello from local GCS emulator!") # [cite: 204]
                # logger.info(f"Blob {blob.name} uploaded (local).")
                # logger.info(f"Blob content: {blob.download_as_text()} (local).")
                # blob.delete()
                # bucket.delete()
                # logger.info("Cleaned up bucket and blob (local).")
                # gcs_emulator_local.clear_data()
            # except Exception as e:
                # logger.error(f"Error interacting with GCS emulator (local): {e}")
    # except RuntimeError as e:
        # logger.error(f"Failed to run GCS emulator (local): {e}")
    # except ImportError:
        # logger.warning("google-cloud-storage library not installed. Skipping GCS local example.")


    logger.info("\n" + "="*30 + "\n")

    # Test GCS Emulator (Docker)
    # Ensure Docker is running for this part
    if shutil.which("docker"):
        try:
            with gcs_emulator_context(port=9092, use_docker=True, host_data_path=os.path.join(os.path.dirname(__file__), 'gcs_data_docker')) as gcs_emulator_docker:
                logger.info(f"GCS Emulator (Docker) Host: {os.getenv('STORAGE_EMULATOR_HOST')}")
                # Here you would run tests that use GCS
                from google.cloud import storage
                try:
                    storage_client_docker = storage.Client(project=gcs_emulator_docker.project_id)
                    bucket_name_docker = f"{gcs_emulator_docker.project_id}-my-bucket-docker"
                    bucket_docker = storage_client_docker.create_bucket(bucket_name_docker)
                    logger.info(f"Bucket {bucket_docker.name} created (Docker).")
                    blob_docker = bucket_docker.blob("test_docker.txt")
                    blob_docker.upload_from_string("Hello from Docker GCS emulator!")
                    logger.info(f"Blob {blob_docker.name} uploaded (Docker).")
                    logger.info(f"Blob content: {blob_docker.download_as_text()} (Docker).")
                    blob_docker.delete()
                    bucket_docker.delete()
                    logger.info("Cleaned up bucket and blob (Docker).")
                    gcs_emulator_docker.clear_data()
                except Exception as e:
                    logger.error(f"Error interacting with GCS emulator (Docker): {e}")
        except RuntimeError as e:
            logger.error(f"Failed to run GCS emulator (Docker): {e}")
        except ImportError:
            logger.warning("google-cloud-storage library not installed. Skipping GCS Docker example.")

    else:
        logger.warning("Docker is not installed or not in PATH. Skipping GCS Docker emulator example.")