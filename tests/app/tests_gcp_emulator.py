# common_utils/test_gcp_emulator.py
import pytest
import os
import shutil
import uuid
import logging
from google.cloud.exceptions import NotFound
from google.cloud import firestore as google_firestore # Explicit import for type hints
from google.cloud import storage as google_storage     # Explicit import for type hints

from common_utils.gcp_emulator import FirestoreEmulator, GCSEmulator, firestore_emulator_context, gcs_emulator_context

logger = logging.getLogger(__name__)
TEST_PROJECT_ID = "pytest-emulator-project"

# --- Firestore Emulator Tests ---

@pytest.fixture(scope="session")
def firestore_emulator_instance():
    """Session-scoped Firestore emulator instance (in-memory)."""
    port = 8088
    emulator = FirestoreEmulator(project_id=TEST_PROJECT_ID, port=port)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

@pytest.fixture
def firestore_client(firestore_emulator_instance: FirestoreEmulator) -> google_firestore.Client:
    """Provides a Firestore client connected to the session-scoped emulator."""
    firestore_emulator_instance.clear_data()
    client = google_firestore.Client(project=firestore_emulator_instance.project_id)
    return client

def test_firestore_emulator_starts_and_stops(firestore_emulator_instance: FirestoreEmulator):
    assert os.getenv("FIRESTORE_EMULATOR_HOST") is not None
    client = google_firestore.Client(project=firestore_emulator_instance.project_id)
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
    assert doc_ref.get().exists

    firestore_emulator_instance.clear_data()

    retrieved_doc = firestore_client.collection(collection_name).document(doc_id).get()
    assert not retrieved_doc.exists

def test_firestore_emulator_context_manager():
    temp_project_id = "fs-context-test"
    port = 8083
    with firestore_emulator_context(project_id=temp_project_id, port=port) as emulator_instance:
        assert os.getenv("FIRESTORE_EMULATOR_HOST") == f"localhost:{port}"
        client = google_firestore.Client(project=emulator_instance.project_id)
        assert client.project == temp_project_id
        doc_ref = client.collection("context_users").document("testuser")
        doc_ref.set({"name": "Context Test"})
        assert doc_ref.get().to_dict()["name"] == "Context Test"
    assert os.getenv("FIRESTORE_EMULATOR_HOST") is None

# --- GCS Emulator Tests ---

@pytest.fixture(scope="session")
def gcs_emulator_instance():
    """Session-scoped GCS emulator instance."""
    port = 9090
    emulator = GCSEmulator(project_id=TEST_PROJECT_ID, port=port)
    try:
        emulator.start()
        yield emulator
    finally:
        emulator.stop()

@pytest.fixture
def gcs_client(gcs_emulator_instance: GCSEmulator) -> google_storage.Client:
    """Provides a GCS client connected to the session-scoped emulator."""
    gcs_emulator_instance.clear_data()
    client = google_storage.Client(project=gcs_emulator_instance.project_id)
    return client

def test_gcs_emulator_starts_and_stops(gcs_emulator_instance: GCSEmulator):
    assert os.getenv("STORAGE_EMULATOR_HOST") is not None
    client = google_storage.Client(project=gcs_emulator_instance.project_id)
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
    bucket = gcs_client.create_bucket(bucket_name)

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

    assert bucket.get_blob(blob_name) is not None
    blob.delete()
    assert bucket.get_blob(blob_name) is None

def test_gcs_delete_bucket(gcs_client: google_storage.Client):
    bucket_name = f"delete-bucket-test-{uuid.uuid4().hex}"
    bucket = gcs_client.create_bucket(bucket_name)

    blob = bucket.blob("some_file_in_bucket.txt")
    blob.upload_from_string("data")

    bucket.delete(force=True)

    with pytest.raises(NotFound):
        gcs_client.get_bucket(bucket_name)

def test_gcs_clear_data(gcs_emulator_instance: GCSEmulator, gcs_client: google_storage.Client):
    # Create buckets and objects
    bucket_names = [f"clear-test-bucket-{i}-{uuid.uuid4().hex[:6]}" for i in range(2)]
    for name in bucket_names:
        bucket = gcs_client.create_bucket(name)
        bucket.blob(f"file_in_{name}.txt").upload_from_string("dummy")

    assert len(list(gcs_client.list_buckets())) >= 2

    gcs_emulator_instance.clear_data()

    # After clearing, buckets should be gone
    for name in bucket_names:
        with pytest.raises(NotFound):
            gcs_client.get_bucket(name)

def test_gcs_emulator_context_manager():
    temp_project_id = "gcs-context-test"
    port = 9093

    with gcs_emulator_context(project_id=temp_project_id, port=port) as emulator_instance:
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
        with pytest.raises(NotFound):
            client.get_bucket(bucket_name)

    assert os.getenv("STORAGE_EMULATOR_HOST") is None