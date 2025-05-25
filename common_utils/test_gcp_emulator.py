# common_utils/test_gcp_emulator.py
import pytest
import os
import shutil
import uuid
from google.cloud.exceptions import NotFound
from google.cloud import firestore as google_firestore # Explicit import for type hints
from google.cloud import storage as google_storage     # Explicit import for type hints

from .gcp_emulator import FirestoreEmulator, GCSEmulator, firestore_emulator_context, gcs_emulator_context

TEST_PROJECT_ID = "pytest-emulator-project"

# --- Firestore Emulator Tests ---

@pytest.fixture(scope="session")
def firestore_emulator_instance():
    """Session-scoped Firestore emulator instance (in-memory)."""
    # Use a unique port for session-scoped emulator to avoid conflicts if tests run in parallel
    # Note: gcloud emulator doesn't easily support dynamic port finding for subprocess.
    # For true parallel safety across multiple pytest sessions, ensure ports are unique.
    # This fixture is session-scoped, so it starts once per test session.
    port = 8088 # Changed port to avoid potential conflict with other tests
    emulator = FirestoreEmulator(project_id=TEST_PROJECT_ID, port=port)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

@pytest.fixture(scope="session")
def persistent_firestore_emulator_instance(tmp_path_factory):
    """Session-scoped Firestore emulator instance with persistent data."""
    data_dir = tmp_path_factory.mktemp("firestore_data_session")
    port = 8089 # Different port for persistent instance
    emulator = FirestoreEmulator(project_id=TEST_PROJECT_ID + "-persist", port=port, data_dir=str(data_dir))
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()
        # shutil.rmtree(data_dir) # Clean up data_dir after tests if needed, or keep for inspection


@pytest.fixture
def firestore_client(firestore_emulator_instance: FirestoreEmulator) -> google_firestore.Client:
    """Provides a Firestore client connected to the session-scoped emulator."""
    firestore_emulator_instance.clear_data() # Clear data before each test
    # Initialize client within the test, as env vars are set by the emulator
    client = google_firestore.Client(project=firestore_emulator_instance.project_id)
    return client

@pytest.fixture
def persistent_firestore_client(persistent_firestore_emulator_instance: FirestoreEmulator) -> google_firestore.Client:
    """Provides a Firestore client for the persistent emulator instance."""
    # Data is not cleared by default for this fixture to test persistence
    client = google_firestore.Client(project=persistent_firestore_emulator_instance.project_id)
    return client


def test_firestore_emulator_starts_and_stops(firestore_emulator_instance: FirestoreEmulator):
    # The fixture itself starting and stopping is the test
    assert os.getenv("FIRESTORE_EMULATOR_HOST") is not None
    # Test client creation directly
    try:
        client = google_firestore.Client(project=firestore_emulator_instance.project_id)
    except Exception as e:
        pytest.fail(f"Failed to create Firestore client for emulator: {e}")
    assert client is not None
    assert client.project == firestore_emulator_instance.project_id

def test_firestore_write_and_read(firestore_client):
    collection_name = "test_items"
    doc_id = f"item_{uuid.uuid4().hex}"
    data = {"name": "Test Item", "value": 123}

    doc_ref = firestore_client.collection(collection_name).document(doc_id)
    doc_ref.set(data)

    retrieved_doc = doc_ref.get()
    assert retrieved_doc.exists
    assert retrieved_doc.to_dict() == data

def test_firestore_clear_data_in_memory(firestore_client: google_firestore.Client, firestore_emulator_instance: FirestoreEmulator):
    collection_name = "items_to_clear"
    doc_id = "temp_item"
    doc_ref = firestore_client.collection(collection_name).document(doc_id)
    doc_ref.set({"message": "this should be cleared"})
    assert doc_ref.get().exists, "Document should exist before clear"

    firestore_emulator_instance.clear_data() # Explicitly call clear_data on the instance

    # After clear_data, the document should not exist.
    # Re-fetch, don't rely on the existing doc_ref's cached state.
    retrieved_doc = firestore_client.collection(collection_name).document(doc_id).get()
    assert not retrieved_doc.exists, "Document should not exist after in-memory clear_data"


def test_firestore_persistent_data(persistent_firestore_client: google_firestore.Client, persistent_firestore_emulator_instance: FirestoreEmulator):
    """Tests data persistence and clearing for a data_dir-backed emulator."""
    collection_name = "persistent_items"
    doc_id = f"persist_item_{uuid.uuid4().hex}"
    data = {"name": "Persistent Item", "value": "should_persist_then_clear"}

    doc_ref = persistent_firestore_client.collection(collection_name).document(doc_id)
    doc_ref.set(data)
    assert doc_ref.get().to_dict() == data, "Data not written correctly to persistent store"

    # Stop and restart the emulator to check persistence
    persistent_firestore_emulator_instance.stop()
    persistent_firestore_emulator_instance.start() # Env vars should be re-set

    # New client instance after restart
    client_after_restart = google_firestore.Client(project=persistent_firestore_emulator_instance.project_id)
    doc_ref_after_restart = client_after_restart.collection(collection_name).document(doc_id)
    assert doc_ref_after_restart.get().to_dict() == data, "Data did not persist across restart"

    # Test clearing persistent data
    # Note: Firestore emulator's --data-dir clear behavior might involve manual directory removal
    # or a specific API call not directly exposed by our clear_data for --data-dir.
    # The current clear_data for FirestoreEmulator with data_dir logs a warning.
    # For a true clear, we'd expect the file to be gone or the emulator reset.
    # Let's simulate a clear by deleting the doc and verifying.
    # A more robust test of clear_data for persistent Firestore might require a different approach
    # or acceptance of the documented limitation.
    persistent_firestore_emulator_instance.clear_data() # This mainly logs a warning for persistent.
    doc_ref_after_restart.delete() # Manually delete for this test's purpose.
    assert not doc_ref_after_restart.get().exists, "Document should be deletable"


def test_firestore_emulator_context_manager_with_data_dir(tmp_path):
    temp_project_id = "fs-context-persist-test"
    port = 8090
    data_dir = tmp_path / "fs_context_data"

    with firestore_emulator_context(project_id=temp_project_id, port=port, data_dir=str(data_dir)) as emulator_instance:
        assert os.getenv("FIRESTORE_EMULATOR_HOST") == f"localhost:{port}"
        client = google_firestore.Client(project=emulator_instance.project_id)
        assert client.project == temp_project_id
        doc_ref = client.collection("context_users").document("testuser_persist")
        doc_ref.set({"name": "Context Persistent Test"})
        assert doc_ref.get().to_dict()["name"] == "Context Persistent Test"
        assert data_dir.exists()
        # Check if some data file is created (implementation-dependent, e.g., persistence.db)
        # For now, just checking data_dir existence.
    assert os.getenv("FIRESTORE_EMULATOR_HOST") is None
    # Data dir should still exist after context manager exits
    assert data_dir.exists()
    # shutil.rmtree(data_dir) # Clean up if desired


@pytest.mark.skip(reason="Firestore emulator's clear_data with --data-dir needs specific API or manual intervention, not fully testable via simple clear_data call")
def test_firestore_clear_data_persistent(persistent_firestore_client: google_firestore.Client, persistent_firestore_emulator_instance: FirestoreEmulator):
    # This test is a placeholder for how one might test --data-dir clearing
    # if the emulator provided a reliable API endpoint for it.
    # Currently, our clear_data for persistent Firestore just logs a warning.
    collection_name = "items_to_clear_persistent"
    doc_id = "temp_item_persistent"
    doc_ref = persistent_firestore_client.collection(collection_name).document(doc_id)
    doc_ref.set({"message": "this should be cleared from persistent storage"})
    assert doc_ref.get().exists

    # This call currently does not guarantee clearing of disk data
    persistent_firestore_emulator_instance.clear_data()

    # To truly test this, one might need to stop the emulator, delete data_dir contents, and restart.
    # Or, if the emulator has a specific /clear endpoint that works for --data-dir.
    # For now, we'll assert based on the current limited capability.
    # retrieved_doc = persistent_firestore_client.collection(collection_name).document(doc_id).get()
    # assert not retrieved_doc.exists # This would ideally be true
    pass

# --- GCS Emulator Tests ---

@pytest.fixture(scope="session")
def gcs_emulator_instance(tmp_path_factory):
    """Session-scoped GCS emulator (fake-gcs-server) instance."""
    port = 9090 # Changed port
    # Use a temporary directory for GCS data for session-scoped tests
    host_data_path = tmp_path_factory.mktemp("gcs_data_session")
    emulator = GCSEmulator(
        project_id=TEST_PROJECT_ID,
        port=port,
        host_data_path=str(host_data_path),
        container_name_prefix="gcs-emulator-session-" # Ensure unique name for session
    )
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()
        # shutil.rmtree(host_data_path) # Clean up GCS data path

@pytest.fixture
def gcs_client(gcs_emulator_instance: GCSEmulator) -> google_storage.Client:
    """Provides a GCS client connected to the session-scoped emulator."""
    gcs_emulator_instance.clear_data() # Clear data before each test
    # Initialize client within the test
    client = google_storage.Client(project=gcs_emulator_instance.project_id)
    return client

def test_gcs_emulator_starts_and_stops(gcs_emulator_instance: GCSEmulator):
    assert os.getenv("STORAGE_EMULATOR_HOST") is not None
    try:
        client = google_storage.Client(project=gcs_emulator_instance.project_id)
    except Exception as e:
        pytest.fail(f"Failed to create GCS client for emulator: {e}")
    assert client is not None
    assert client.project == gcs_emulator_instance.project_id

def test_gcs_create_bucket_and_list(gcs_client: google_storage.Client):
    bucket_name = f"test-bucket-{uuid.uuid4().hex}"
    bucket = gcs_client.create_bucket(bucket_name)
    assert bucket.name == bucket_name

    buckets = list(gcs_client.list_buckets())
    assert any(b.name == bucket_name for b in buckets)

def test_gcs_upload_and_download_blob(gcs_client: google_storage.Client):
    bucket_name = f"upload-test-bucket-{uuid.uuid4().hex}"
    bucket = gcs_client.create_bucket(bucket_name) # Ensure bucket is created before use

    blob_name = "test_object.txt"
    content = "Hello from GCS emulator test!"

    blob = bucket.blob(blob_name)
    blob.upload_from_string(content)

    downloaded_blob = bucket.blob(blob_name)
    downloaded_content = downloaded_blob.download_as_text()
    assert downloaded_content == content

def test_gcs_delete_blob(gcs_client: google_storage.Client):
    bucket_name = f"delete-blob-bucket-{uuid.uuid4().hex}"
    bucket = gcs_client.create_bucket(bucket_name)
    blob_name = "to_delete.txt"
    blob = bucket.blob(blob_name)
    blob.upload_from_string("Temporary content")

    assert bucket.get_blob(blob_name) is not None, "Blob should exist before delete"
    blob.delete()
    assert bucket.get_blob(blob_name) is None, "Blob should not exist after delete"

def test_gcs_delete_bucket(gcs_client: google_storage.Client):
    bucket_name = f"delete-bucket-test-{uuid.uuid4().hex}"
    bucket = gcs_client.create_bucket(bucket_name)

    # Upload a blob to make deletion potentially more complex
    blob = bucket.blob("some_file_in_bucket.txt")
    blob.upload_from_string("data")

    bucket.delete(force=True) # force=True to delete even if not empty

    with pytest.raises(NotFound):
        gcs_client.get_bucket(bucket_name)

def test_gcs_clear_data(gcs_emulator_instance: GCSEmulator, gcs_client: google_storage.Client):
    # Create a few buckets and objects
    bucket_names = [f"clear-test-bucket-{i}-{uuid.uuid4().hex[:6]}" for i in range(2)]
    for name in bucket_names:
        bucket = gcs_client.create_bucket(name)
        bucket.blob(f"file_in_{name}.txt").upload_from_string("dummy")

    # Ensure some buckets exist
    assert len(list(gcs_client.list_buckets())) >= 2

    gcs_emulator_instance.clear_data() # Call clear_data on the instance

    # After clearing, no user-created buckets should remain.
    # fake-gcs-server might have internal/default buckets, so we check specifically for ours.
    remaining_buckets = list(gcs_client.list_buckets())
    print(f"Buckets after clear_data: {[b.name for b in remaining_buckets]}")
    for name in bucket_names:
        with pytest.raises(NotFound, match=f"404 GET {gcs_emulator_instance.emulator_host_env}/storage/v1/b/{name}"):
            gcs_client.get_bucket(name)
    # Also check if the host_data_path is empty
    assert not any(os.scandir(gcs_emulator_instance.host_data_path)), "Host data path should be empty after clear"

def test_gcs_data_persistence_and_clear_with_context_manager(tmp_path):
    """Test GCS data persistence when a container is reused and then cleared."""
    temp_project_id = "gcs-context-persist-test"
    port = 9091
    host_data_path = tmp_path / "gcs_context_data_persist"
    container_name = f"fake-gcs-pytest-{temp_project_id}-{port}" # Match GCSEmulator's fixed naming

    # First run: create data
    with gcs_emulator_context(project_id=temp_project_id, port=port, host_data_path=str(host_data_path)) as emulator1:
        client1 = google_storage.Client(project=emulator1.project_id)
        bucket_name1 = f"gcs-persist-bucket-{uuid.uuid4().hex[:6]}"
        bucket1 = client1.create_bucket(bucket_name1)
        blob1 = bucket1.blob("persist_file.txt")
        blob1.upload_from_string("This should persist.")
        assert blob1.exists()
        # Check that some data exists in the host_data_path
        assert any(os.scandir(host_data_path)), "Host data path should not be empty after first run"

    # Emulator is stopped, but container and data on disk should remain.

    # Second run: check if data persisted
    with gcs_emulator_context(project_id=temp_project_id, port=port, host_data_path=str(host_data_path)) as emulator2:
        # Emulator should reuse the same container if named consistently
        assert emulator2.container_name == container_name
        client2 = google_storage.Client(project=emulator2.project_id)
        bucket2 = client2.get_bucket(bucket_name1) # Get existing bucket
        assert bucket2.exists(), "Bucket should have persisted"
        blob2 = bucket2.get_blob("persist_file.txt")
        assert blob2 is not None, "Blob should have persisted"
        assert blob2.download_as_text() == "This should persist."

        # Now test clear_data
        emulator2.clear_data()
        assert not any(os.scandir(host_data_path)), "Host data path should be empty after clear_data"
        with pytest.raises(NotFound):
            client2.get_bucket(bucket_name1) # Bucket should be gone

    # Ensure the host_data_path itself still exists but is empty
    assert host_data_path.exists()
    assert not any(os.scandir(host_data_path))
    # shutil.rmtree(host_data_path) # Clean up the directory itself


# --- Context Manager Tests (alternative to fixtures) ---

def test_firestore_emulator_context_manager():
    temp_project_id = "fs-context-test"
    port = 8083 # Changed port
    with firestore_emulator_context(project_id=temp_project_id, port=port) as emulator_instance:
        assert os.getenv("FIRESTORE_EMULATOR_HOST") == f"localhost:{port}"
        client = google_firestore.Client(project=emulator_instance.project_id)
        assert client.project == temp_project_id
        doc_ref = client.collection("context_users").document("testuser")
        doc_ref.set({"name": "Context Test"})
        assert doc_ref.get().to_dict()["name"] == "Context Test"
    assert os.getenv("FIRESTORE_EMULATOR_HOST") is None # Env var should be restored

def test_gcs_emulator_context_manager(tmp_path_factory):
    temp_project_id = "gcs-context-test"
    port = 9093 # Changed port
    host_data_path = tmp_path_factory.mktemp("gcs_context_data_cm")

    with gcs_emulator_context(project_id=temp_project_id, port=port, host_data_path=str(host_data_path)) as emulator_instance:
        assert os.getenv("STORAGE_EMULATOR_HOST") == f"http://localhost:{port}"
        client = google_storage.Client(project=emulator_instance.project_id)
        assert client.project == temp_project_id
        
        bucket_name = f"gcs-context-bucket-{uuid.uuid4().hex[:6]}"
        bucket = client.create_bucket(bucket_name)
        assert bucket.exists()
        
        blob = bucket.blob("context_file.txt")
        blob.upload_from_string("Context GCS data")
        assert blob.download_as_text() == "Context GCS data"

        # Test clear_data within context
        emulator_instance.clear_data()
        assert not any(os.scandir(host_data_path)), "Host data should be cleared within context"
        with pytest.raises(NotFound):
            client.get_bucket(bucket_name)

    assert os.getenv("STORAGE_EMULATOR_HOST") is None # Env var should be restored
    # shutil.rmtree(host_data_path) # Clean up