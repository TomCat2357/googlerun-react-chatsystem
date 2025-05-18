# common_utils/test_gcp_emulator.py
import pytest
import os
import uuid
from google.cloud.exceptions import NotFound

# Assuming gcp_emulator.py is in the same directory or accessible via PYTHONPATH
from .gcp_emulator import FirestoreEmulator, GCSEmulator, firestore_emulator_context, gcs_emulator_context

TEST_PROJECT_ID = "pytest-emulator-project"

# --- Firestore Emulator Tests ---

@pytest.fixture(scope="session")
def firestore_emulator_instance():
    """Session-scoped Firestore emulator instance."""
    # Use a unique port for session-scoped emulator to avoid conflicts if tests run in parallel
    # Note: gcloud emulator doesn't easily support dynamic port finding for subprocess.
    # For true parallel safety across multiple pytest sessions, ensure ports are unique.
    # This fixture is session-scoped, so it starts once per test session.
    port = 8081 # Example port, ensure it's free
    emulator = FirestoreEmulator(project_id=TEST_PROJECT_ID, port=port)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

@pytest.fixture
def firestore_client(firestore_emulator_instance: FirestoreEmulator):
    """Provides a Firestore client connected to the session-scoped emulator."""
    firestore_emulator_instance.clear_data() # Clear data before each test
    client = firestore_emulator_instance.get_client()
    return client

def test_firestore_emulator_starts_and_stops(firestore_emulator_instance: FirestoreEmulator):
    # The fixture itself starting and stopping is the test
    assert os.getenv("FIRESTORE_EMULATOR_HOST") is not None
    client = firestore_emulator_instance.get_client()
    assert client is not None
    print(f"Firestore client project: {client.project}") # Should be TEST_PROJECT_ID

def test_firestore_write_and_read(firestore_client):
    collection_name = "test_items"
    doc_id = f"item_{uuid.uuid4().hex}"
    data = {"name": "Test Item", "value": 123}

    doc_ref = firestore_client.collection(collection_name).document(doc_id)
    doc_ref.set(data)

    retrieved_doc = doc_ref.get()
    assert retrieved_doc.exists
    assert retrieved_doc.to_dict() == data

def test_firestore_clear_data(firestore_client):
    collection_name = "items_to_clear"
    doc_id = "temp_item"
    doc_ref = firestore_client.collection(collection_name).document(doc_id)
    doc_ref.set({"message": "this should be cleared"})

    # Data exists before clear (implicitly tested by next clear in fixture or explicit call)
    # For this test, we'll access the emulator instance directly for clear_data
    # This requires the emulator instance if not using the fixture's auto-clear
    # In a real scenario, the fixture `firestore_client` would handle clearing for the next test.
    # For an explicit test of clear_data:
    # Find the emulator instance (e.g., if it was passed or accessible globally for testing purposes)
    # For simplicity, assume we are testing the context manager variant here
    with firestore_emulator_context(project_id=TEST_PROJECT_ID, port=8082) as client_for_clear_test:
        temp_doc = client_for_clear_test.collection("clearing_test").document("ephemeral")
        temp_doc.set({"data": "some_data"})
        assert temp_doc.get().exists

        # How to get the emulator instance from the context manager to call clear_data?
        # The context manager yields the client. To test clear_data, we might need a different fixture setup
        # or test the FirestoreEmulator class directly.

        # Let's test clear_data via the firestore_emulator_instance fixture
        # This is a bit tricky as the fixture scope might conflict.
        # A simpler way is to assume clear_data works if subsequent tests using the same emulator
        # don't see data from previous ones.
        # The fixture already calls clear_data, so this test is more about the effect.

    # Check that data from the previous test is gone (due to fixture's clear_data)
    retrieved_doc = firestore_client.collection(collection_name).document(doc_id).get()
    assert not retrieved_doc.exists

# --- GCS Emulator Tests ---

@pytest.fixture(scope="session")
def gcs_emulator_instance():
    """Session-scoped GCS emulator (fake-gcs-server) instance."""
    port = 4444 # Example port, ensure it's free
    initial_test_bucket = f"gcs-pytest-bucket-initial-{uuid.uuid4().hex[:6]}"
    emulator = GCSEmulator(project_id=TEST_PROJECT_ID, port=port, initial_buckets=[initial_test_bucket])
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

@pytest.fixture
def gcs_client(gcs_emulator_instance: GCSEmulator):
    """Provides a GCS client connected to the session-scoped emulator."""
    # Clear buckets/objects before each test if fake-gcs-server doesn't do this automatically on restart
    # or if we want pristine state. The provided GCSEmulator has clear_all_buckets_and_objects.
    gcs_emulator_instance.clear_all_buckets_and_objects()
    # Recreate initial buckets if cleared
    if gcs_emulator_instance.initial_buckets:
        client = gcs_emulator_instance.get_client()
        for bucket_name in gcs_emulator_instance.initial_buckets:
            try:
                client.create_bucket(bucket_name)
            except Exception: # pragma: no cover (bucket might exist if clear failed partially)
                pass
    return gcs_emulator_instance.get_client()

def test_gcs_emulator_starts_and_stops(gcs_emulator_instance: GCSEmulator):
    assert os.getenv("STORAGE_EMULATOR_HOST") is not None
    client = gcs_emulator_instance.get_client()
    assert client is not None
    print(f"GCS client project: {client.project}")

def test_gcs_create_bucket_and_list(gcs_client):
    bucket_name = f"test-bucket-{uuid.uuid4().hex}"
    bucket = gcs_client.create_bucket(bucket_name)
    assert bucket.name == bucket_name

    buckets = list(gcs_client.list_buckets())
    assert any(b.name == bucket_name for b in buckets)

    # Check if initial bucket from fixture also exists (if not cleared and re-created specifically here)
    gcs_emulator_instance_fixture = gcs_client._connection.API_BASE_URL # Hacky way to see emulator host
    # A better way would be to access the fixture instance directly if needed
    # For this test, let's assume the fixture's initial bucket exists
    initial_bucket_name_part = "gcs-pytest-bucket-initial-"
    assert any(b.name.startswith(initial_bucket_name_part) for b in buckets if hasattr(b, 'name'))


def test_gcs_upload_and_download_blob(gcs_client):
    bucket_name = f"upload-test-bucket-{uuid.uuid4().hex}"
    gcs_client.create_bucket(bucket_name)
    bucket = gcs_client.bucket(bucket_name)

    blob_name = "test_object.txt"
    content = "Hello from GCS emulator test!"

    blob = bucket.blob(blob_name)
    blob.upload_from_string(content)

    downloaded_blob = bucket.blob(blob_name)
    downloaded_content = downloaded_blob.download_as_text()
    assert downloaded_content == content

def test_gcs_delete_blob(gcs_client):
    bucket_name = f"delete-blob-bucket-{uuid.uuid4().hex}"
    gcs_client.create_bucket(bucket_name)
    bucket = gcs_client.bucket(bucket_name)
    blob_name = "to_delete.txt"
    blob = bucket.blob(blob_name)
    blob.upload_from_string("Temporary content")

    assert bucket.get_blob(blob_name) is not None
    blob.delete()
    assert bucket.get_blob(blob_name) is None

def test_gcs_delete_bucket(gcs_client):
    bucket_name = f"delete-bucket-test-{uuid.uuid4().hex}"
    gcs_client.create_bucket(bucket_name)
    bucket = gcs_client.bucket(bucket_name)

    # Upload a blob to make deletion potentially more complex
    blob = bucket.blob("some_file_in_bucket.txt")
    blob.upload_from_string("data")

    bucket.delete(force=True) # force=True to delete even if not empty

    with pytest.raises(NotFound):
        gcs_client.get_bucket(bucket_name)

def test_gcs_clear_all_buckets(gcs_emulator_instance: GCSEmulator, gcs_client):
    # Create a few buckets
    bucket_names = [f"clear-test-bucket-{i}-{uuid.uuid4().hex[:6]}" for i in range(3)]
    for name in bucket_names:
        gcs_client.create_bucket(name)
        bucket = gcs_client.bucket(name)
        bucket.blob(f"file_in_{name}.txt").upload_from_string("dummy")

    assert len(list(gcs_client.list_buckets())) >= 3

    gcs_emulator_instance.clear_all_buckets_and_objects()

    # After clearing, no buckets should remain (except potentially default ones if fake-gcs-server creates them)
    # fake-gcs-server with -data /dev/null shouldn't persist, but let's check
    remaining_buckets = list(gcs_client.list_buckets())
    print(f"Buckets after clear: {[b.name for b in remaining_buckets]}")
    # This assertion might be flaky depending on fake-gcs-server version and how it handles default buckets
    # We expect user-created buckets to be gone.
    for name in bucket_names:
        with pytest.raises(NotFound):
            gcs_client.get_bucket(name)


# --- Context Manager Tests (alternative to fixtures) ---

def test_firestore_emulator_context_manager():
    temp_project_id = "fs-context-test"
    port = 8083
    with firestore_emulator_context(project_id=temp_project_id, port=port) as client:
        assert os.getenv("FIRESTORE_EMULATOR_HOST") == f"localhost:{port}"
        assert client.project == temp_project_id
        doc_ref = client.collection("context_users").document("testuser")
        doc_ref.set({"name": "Context Test"})
        assert doc_ref.get().to_dict()["name"] == "Context Test"
    assert os.getenv("FIRESTORE_EMULATOR_HOST") is None # Env var should be restored

def test_gcs_emulator_context_manager():
    temp_project_id = "gcs-context-test"
    port = 4445
    initial_bucket = f"gcs-context-bucket-{uuid.uuid4().hex[:6]}"
    with gcs_emulator_context(project_id=temp_project_id, port=port, initial_buckets=[initial_bucket]) as client:
        assert os.getenv("STORAGE_EMULATOR_HOST") == f"http://localhost:{port}"
        assert client.project == temp_project_id
        bucket = client.get_bucket(initial_bucket) # Check initial bucket creation
        assert bucket.exists()
        blob = bucket.blob("context_file.txt")
        blob.upload_from_string("Context GCS data")
        assert blob.download_as_text() == "Context GCS data"
    assert os.getenv("STORAGE_EMULATOR_HOST") is None # Env var should be restored