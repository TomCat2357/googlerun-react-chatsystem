# common_utils/gcp_emulator.py
import os
import subprocess
import time
import uuid
from contextlib import contextmanager

from google.cloud import firestore
from google.cloud import storage

# Default ports, can be overridden
DEFAULT_FIRESTORE_PORT = 8080
DEFAULT_GCS_PORT = 4443
DEFAULT_GCS_EXTERNAL_URL = f"http://localhost:{DEFAULT_GCS_PORT}"

class EmulatorManager:
    """Base class for managing emulator processes."""
    def __init__(self, project_id="test-project"):
        self.project_id = project_id
        self.process = None
        self.original_env_vars = {}

    def _set_env_var(self, key, value):
        self.original_env_vars[key] = os.environ.get(key)
        os.environ[key] = value

    def _restore_env_vars(self):
        for key, value in self.original_env_vars.items():
            if value is None:
                del os.environ[key]
            else:
                os.environ[key] = value
        self.original_env_vars.clear()

    def start(self):
        raise NotImplementedError

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            print(f"{self.__class__.__name__} process stopped.")
            self.process = None
        self._restore_env_vars()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class FirestoreEmulator(EmulatorManager):
    """Manages the Google Cloud Firestore emulator."""
    def __init__(self, project_id="test-project", port=DEFAULT_FIRESTORE_PORT, host="localhost"):
        super().__init__(project_id)
        self.port = port
        self.host = host
        self.emulator_host = f"{self.host}:{self.port}"

    def start(self):
        print(f"Starting Firestore emulator on {self.emulator_host} for project {self.project_id}...")
        try:
            # Check if gcloud is available
            subprocess.run(["gcloud", "--version"], capture_output=True, check=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("ERROR: gcloud CLI is not installed or not in PATH. Firestore emulator cannot be started.")
            print("Please install Google Cloud SDK: https://cloud.google.com/sdk/docs/install")
            raise RuntimeError("gcloud CLI not found, cannot start Firestore emulator.")

        self.process = subprocess.Popen(
            ["gcloud", "emulators", "firestore", "start",
             f"--project={self.project_id}",
             f"--host-port={self.emulator_host}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Wait for emulator to be ready - gcloud emulator output is not always immediate
        time.sleep(5) # Adjust as necessary, or implement a more robust check
        self._set_env_var("FIRESTORE_EMULATOR_HOST", self.emulator_host)
        print(f"Firestore emulator started. FIRESTORE_EMULATOR_HOST set to {self.emulator_host}")

    def get_client(self):
        """Returns a Firestore client configured to use the emulator."""
        if not os.getenv("FIRESTORE_EMULATOR_HOST"):
            raise RuntimeError("FIRESTORE_EMULATOR_HOST is not set. Ensure emulator is running.")
        return firestore.Client(project=self.project_id)

    def clear_data(self):
        """Clears all data from the Firestore emulator."""
        import requests
        try:
            requests.delete(f"http://{self.emulator_host}/emulator/v1/projects/{self.project_id}/databases/(default)/documents")
            print("Firestore emulator data cleared.")
        except requests.exceptions.ConnectionError:
            print(f"Could not connect to Firestore emulator at {self.emulator_host} to clear data.")
        except Exception as e:
            print(f"Error clearing Firestore data: {e}")


class GCSEmulator(EmulatorManager):
    """
    Manages the fake-gcs-server emulator for Google Cloud Storage.
    Requires fake-gcs-server to be installed and in PATH.
    See: https://github.com/fsouza/fake-gcs-server
    """
    def __init__(self, project_id="test-project", port=DEFAULT_GCS_PORT, host="localhost",
                 initial_buckets=None, external_url=None, in_memory=True):
        super().__init__(project_id)
        self.port = port
        self.host = host
        self.emulator_host_internal = f"{self.host}:{self.port}" # Used by the client library
        self.external_url = external_url or f"http://{self.host}:{self.port}" # Public URL if different
        self.initial_buckets = initial_buckets or []
        self.in_memory = in_memory

    def start(self):
        print(f"Starting GCS emulator (fake-gcs-server) on port {self.port}...")
        command = [
            "fake-gcs-server",
            "-scheme", "http", # fake-gcs-server defaults to https, client library expects http for emulator
            "-port", str(self.port),
            "-host", self.host,
            "-public-host", self.external_url.replace("http://", "").replace("https://", ""), # fake-gcs-server expects just host:port
        ]
        if self.in_memory:
            command.append("-data", "/dev/null") # Or use a temp directory for in-memory behavior

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Wait for emulator to be ready
        time.sleep(3) # Adjust as necessary
        self._set_env_var("STORAGE_EMULATOR_HOST", f"http://{self.emulator_host_internal}") # Client needs http:// prefix
        print(f"GCS emulator started. STORAGE_EMULATOR_HOST set to http://{self.emulator_host_internal}")

        if self.initial_buckets:
            client = self.get_client()
            for bucket_name in self.initial_buckets:
                try:
                    client.create_bucket(bucket_name)
                    print(f"Created initial bucket: {bucket_name}")
                except Exception as e:
                    # Potentially ignore if bucket already exists from a previous run not fully cleaned
                    print(f"Could not create initial bucket {bucket_name} (may already exist): {e}")


    def get_client(self):
        """Returns a GCS client configured to use the emulator."""
        if not os.getenv("STORAGE_EMULATOR_HOST"):
            raise RuntimeError("STORAGE_EMULATOR_HOST is not set. Ensure emulator is running.")
        # When using the emulator, typically no credentials are needed.
        # The google-cloud-storage library will automatically use anonymous credentials
        # if STORAGE_EMULATOR_HOST is set.
        return storage.Client(project=self.project_id)

    def clear_all_buckets_and_objects(self):
        """Clears all objects from all buckets and then deletes the buckets."""
        client = self.get_client()
        try:
            for bucket in client.list_buckets():
                print(f"Clearing bucket: {bucket.name}")
                for blob in bucket.list_blobs():
                    try:
                        blob.delete()
                    except Exception as e_blob:
                        print(f"Error deleting blob {blob.name} from {bucket.name}: {e_blob}")
                try:
                    bucket.delete(force=True) # Force delete even if not empty
                    print(f"Deleted bucket: {bucket.name}")
                except Exception as e_bucket:
                    print(f"Error deleting bucket {bucket.name}: {e_bucket}")
            print("All GCS emulator buckets and objects cleared.")
        except Exception as e:
            print(f"Error clearing GCS data: {e}")


@contextmanager
def firestore_emulator_context(project_id="test-project", port=DEFAULT_FIRESTORE_PORT):
    """Context manager for running tests with Firestore emulator."""
    emulator = FirestoreEmulator(project_id=project_id, port=port)
    try:
        emulator.start()
        yield emulator.get_client()
    finally:
        emulator.stop()

@contextmanager
def gcs_emulator_context(project_id="test-project", port=DEFAULT_GCS_PORT, initial_buckets=None):
    """Context manager for running tests with GCS emulator."""
    emulator = GCSEmulator(project_id=project_id, port=port, initial_buckets=initial_buckets)
    try:
        emulator.start()
        yield emulator.get_client()
    finally:
        emulator.stop()

if __name__ == '__main__':
    # Example usage:
    print("Demonstrating Firestore Emulator Context Manager:")
    with firestore_emulator_context(project_id="my-firestore-test") as fs_client:
        print("Firestore emulator is running.")
        doc_ref = fs_client.collection("users").document("alovelace")
        doc_ref.set({"first": "Ada", "last": "Lovelace", "born": 1815})
        doc = doc_ref.get()
        print(f"Retrieved from Firestore emulator: {doc.to_dict()}")
    print("Firestore emulator context finished.\n")

    print("Demonstrating GCS Emulator Context Manager:")
    test_bucket_name = f"test-bucket-{uuid.uuid4().hex[:6]}"
    with gcs_emulator_context(project_id="my-gcs-test", initial_buckets=[test_bucket_name]) as gcs_client:
        print("GCS emulator is running.")
        bucket = gcs_client.bucket(test_bucket_name)
        assert bucket.exists()
        print(f"Bucket '{test_bucket_name}' exists.")
        blob = bucket.blob("test_file.txt")
        blob.upload_from_string("Hello, GCS emulator!")
        print(f"Uploaded 'test_file.txt' to bucket '{test_bucket_name}'.")
        downloaded_content = blob.download_as_text()
        print(f"Downloaded content: {downloaded_content}")
        assert downloaded_content == "Hello, GCS emulator!"
    print("GCS emulator context finished.")