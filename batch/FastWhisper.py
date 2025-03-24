import time
import io
from google.cloud import storage
from faster_whisper import WhisperModel

# Function to get file data as bytes from GCS
def get_gcs_file_bytes(gcs_uri):
    """Reads a file from GCS as bytes without saving to disk."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError("URI must start with gs://")
    
    # Remove 'gs://' prefix and split into bucket and blob path
    path_without_prefix = gcs_uri[5:]
    bucket_name, blob_path = path_without_prefix.split("/", 1)
    
    # Get the file content
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    # Download into memory
    in_memory_file = io.BytesIO()
    blob.download_to_file(in_memory_file)
    in_memory_file.seek(0)  # Reset the file pointer to the beginning
    
    print(f"Loaded {gcs_uri} into memory")
    return in_memory_file

# GCS URI for your audio file
gcs_uri = "gs://storage_music_test_20250319/sample1.wav"

# Get file bytes from GCS
audio_bytes = get_gcs_file_bytes(gcs_uri)

# Initialize Whisper model with CPU instead of GPU
# Change device to "cpu" and remove compute_type
model = WhisperModel("large", device="cuda")

# Run transcription
now = time.time()

# Save to a temporary file since faster_whisper likely needs a file path
import tempfile
import os

# Create a temporary file
temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
temp_filename = temp_file.name
temp_file.close()

# Write the bytes to the temp file
with open(temp_filename, 'wb') as f:
    f.write(audio_bytes.getvalue())

# Transcribe from the temp file
segments, info = model.transcribe(temp_filename, beam_size=5)

# Clean up
os.unlink(temp_filename)

# Display output
print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

# Write to text file
with open('transcription.txt', 'a', encoding='utf-8') as f:

    for segment in segments:
        print(f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text}")
        print(segment)
        f.write(f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text}\n")
print('spend:', time.time()-now)