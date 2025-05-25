# Project Readme: googlerun-react-chatsystem

## 1. Project Overview

This project is a comprehensive chat system featuring a React frontend and a Python (FastAPI) backend. It integrates various Google Cloud services for enhanced functionalities, including real-time chat, user authentication, image generation, speech-to-text transcription, geocoding services, and advanced batch audio processing with Whisper.

The system is designed with a modular architecture, separating concerns for the frontend, backend, batch processing, and shared utilities. Configuration is managed through environment files, and Docker is utilized for containerizing backend and batch processing components.

## 2. Directory Structure

The project is organized into the following main directories:

* `backend/`: Contains the FastAPI backend application. [cite: 1]
* `frontend/`: Contains the React frontend application. [cite: 1]
* `whisper_batch/`: Houses the batch processing application for audio transcription using Whisper. [cite: 21]
* `common_utils/`: Provides shared utility modules used across different parts of the project, such as logging and GCP emulator management. [cite: 9, 37]
* `tests/`: Includes various test scripts, particularly for backend services and GCP emulator interactions. [cite: 21]
* Root directory: Contains project-wide configuration files (`pytest.ini`), utility scripts (`code_printer.py`, `tree.py`), and Docker-related files. [cite: 1]

## 3. Backend (`backend/`)

The backend is a FastAPI application responsible for handling API requests from the frontend and orchestrating various services. [cite: 2, 178]

### 3.1. Key Functionalities & API Endpoints

* **Authentication (`app/api/auth.py`)**: Manages user authentication using Firebase. [cite: 2, 185] It includes middleware for request logging and token verification. [cite: 185, 188]
* **Chat (`app/api/chat.py`)**: Provides real-time chat functionalities, likely integrating with AI models for responses. [cite: 2, 203]
* **Configuration (`app/api/config.py`)**: Exposes server-side configuration values to the frontend. [cite: 2]
* **Geocoding (`app/api/geocoding.py`)**: Handles address-to-coordinate and coordinate-to-address conversions, utilizing Google Maps API and caching mechanisms. [cite: 3, 223]
* **Image Generation (`app/api/image.py`)**: Integrates with image generation models (e.g., Imagen on VertexAI) to create images based on prompts. [cite: 3, 238]
* **Speech-to-Text (`app/api/speech.py`)**: Provides speech recognition services, likely using Google Cloud Speech-to-Text. [cite: 3, 245]
* **Whisper Transcription (`app/api/whisper.py`)**: Manages audio uploads to GCS, queues transcription jobs in Firestore, and triggers batch processing for Whisper. [cite: 3, 260, 263] It also handles listing jobs and retrieving results. [cite: 298, 313]
* **Whisper Batch Notifications (`app/api/whisper_batch.py`)**: Includes an endpoint to receive and process notifications about the completion or failure of GCP Batch jobs. [cite: 2, 371]

### 3.2. Core Services and Utilities

* **Services (`app/services/`)**: Contains business logic for features like chat, geocoding, image generation, speech processing, and Whisper job queuing. [cite: 4, 5]
* **Audio Utilities (`app/core/audio_utils.py`)**: Provides functions for audio processing, such as probing duration and converting audio formats using `ffprobe` and `ffmpeg`. [cite: 4, 372]
* **File Utilities (`app/utils/file_utils.py`)**: Handles processing of uploaded files, including images (resizing, compression) and various document types (CSV, DOCX). [cite: 5, 485, 496, 502]
* **Maps Utilities (`app/utils/maps.py`)**: Interacts with Google Maps API for static maps, geocoding, and street view. [cite: 6, 511]

### 3.3. Configuration

* Configuration is managed via `.env` files located in `backend/config/` and `backend/config_develop/`. [cite: 7, 525]
* It supports different configurations for development (`.env.develop`) and production. [cite: 7, 525]
* SSL certificates for development are also managed within these directories. [cite: 525]

### 3.4. Deployment

* The backend is containerized using `backend/backend_frontend.dockerfile`, which also copies the built frontend assets. [cite: 176]
* Deployment examples for Google Cloud Run are provided in `gcloud_command例.txt`. [cite: 159]

## 4. Frontend (`frontend/`)

The frontend is a single-page application built with React, Vite, and TypeScript, providing the user interface for the chat system. [cite: 1127]

### 4.1. Key Features and Components

* **Authentication (`src/contexts/AuthContext.tsx`, `src/components/Auth/`)**: Handles user login and session management using Firebase. [cite: 18, 1158, 1665] Protected routes ensure that only authenticated users can access application features. [cite: 19, 1675]
* **Main Navigation (`src/components/Main/MainPage.tsx`)**: Provides a dashboard for accessing different features like Chat, Geocoding, Speech-to-Text, Image Generation, and Whisper. [cite: 15, 1428]
* **Chat Interface (`src/components/Chat/ChatPage.tsx`)**: The core chat UI, allowing users to send messages, attach files (images, audio, text), and receive responses. [cite: 13, 1208] It includes components for message display, input handling, file previews, and a sidebar for managing chat history and model selection. [cite: 12, 13, 1242, 1193, 1167, 1254]
* **Geocoding Page (`src/components/Geocoding/GeocodingPage.tsx`)**: Allows users to perform geocoding (address to coordinates and vice-versa) and view results on a map with satellite and street view options. [cite: 14, 1319] It utilizes IndexedDB for caching results. [cite: 1319]
* **Speech-to-Text Page (`src/components/SpeechToText/SpeechToTextPage.tsx`)**: Enables users to upload audio files and receive transcriptions. [cite: 16, 1487] It features an audio player with transcript synchronization and options to edit and export transcripts. [cite: 16, 1435]
* **Image Generation Page (`src/components/GenerateImage/GenerateImagePage.tsx`)**: Provides an interface for generating images using AI models by inputting prompts and various parameters. [cite: 14, 1265]
* **Whisper Transcription Page (`src/components/Whisper/WhisperPage.tsx`)**: Allows users to upload audio files for batch transcription using Whisper. [cite: 17, 1557] It includes features for job submission, viewing job lists and statuses, and playing back audio with synchronized, speaker-diarized transcripts. [cite: 17, 1515, 1609]
* **File Utilities (`src/utils/fileUtils.ts`)**: Contains functions for client-side processing of uploaded files, including images (resizing, format conversion), PDFs (conversion to images or text extraction using `pdfjs-dist`), DOCX (`mammoth`), and CSV (`xlsx`). [cite: 20, 1681, 1127]
* **Configuration Management (`src/config.ts`)**: Manages frontend configuration, including API endpoints and Firebase settings from `.env.local`. [cite: 11, 1139] It also fetches and stores server-side configurations in IndexedDB. [cite: 1139]

### 4.2. Build and Development

* Uses Vite for fast development and optimized builds. [cite: 10, 629, 1133]
* Scripts for development (`npm run dev`) and building (`npm run build`) are defined in `package.json`. [cite: 1127]
* Tailwind CSS is used for styling. [cite: 10, 1129]
* ESLint is configured for code linting. [cite: 9, 631]

## 5. Whisper Batch Processing (`whisper_batch/`)

This component handles asynchronous, long-running audio transcription and diarization tasks using Whisper models.

### 5.1. Functionality

* **Job Processing (`app/main.py`)**: The main script that polls Firestore for new transcription jobs, downloads audio from GCS, performs transcription using `faster-whisper`, and speaker diarization using `pyannote.audio`. [cite: 23, 1883, 1885, 1856]
* **Transcription (`app/transcribe.py`)**: Contains the logic for audio transcription using the WhisperModel. [cite: 23, 1918]
* **Diarization (`app/diarize.py`)**: Handles speaker diarization using `pyannote.audio.Pipeline`. [cite: 22, 1868]
* **Results Combination (`app/combine_results.py`)**: Merges the transcription and diarization outputs into a single JSON file with speaker-labeled segments. [cite: 22, 1859]
* **Storage**: Uses Google Cloud Storage for storing audio files and transcription results. [cite: 1885, 1901] Job metadata and status are managed in Firestore. [cite: 1883, 1886]

### 5.2. Configuration and Deployment

* Configuration is managed via `.env` files in `whisper_batch/config/` and `whisper_batch/config_develop/`. [cite: 23, 1925, 1926]
* It is designed to be run as a Docker container, with `whisper_batch.dockerfile` provided for building the image. [cite: 22] This Docker image is intended for use with GCP Batch.
* Requires a HuggingFace authentication token (`HF_AUTH_TOKEN`) for `pyannote.audio`. [cite: 1925]

## 6. Common Utilities (`common_utils/`)

This directory contains Python modules shared across the backend and potentially other Python-based components.

* **`logger.py`**: A centralized logging utility, configurable via the `DEBUG` environment variable, with features for data sanitization (masking sensitive keys, truncating long data). [cite: 111, 613, 615]
* **`class_types.py`**: Defines Pydantic models for request and data structures used throughout the application, ensuring data validation and type safety. [cite: 38, 526]
* **`gcp_emulator.py`**: Provides an `EmulatorManager` class and specific implementations for Firestore (`FirestoreEmulator`) and GCS (`GCSEmulator`) emulators. [cite: 537, 541, 552] This is primarily used for local development and testing to simulate GCP services. The GCS emulator uses Docker (`fsouza/fake-gcs-server`) and supports persistent data storage. [cite: 65, 553, 555]
* **`test_gcp_emulator.py`**: Contains Pytest tests for the GCP emulator utilities. [cite: 37]

## 7. Testing (`tests/`)

The project includes a `tests/` directory for automated tests.

* **Backend Tests (`tests/app/`)**:
    * `firebase_t.py`: Appears to be a script for testing Firebase/Firestore interactions, including creating and clearing test data. [cite: 20, 1739]
    * `tests_whisper_batch.py`, `tests_whisper_batch2.py`, etc.: A suite of tests for the `whisper_batch` functionality, likely covering job picking, timeout handling, and processing logic using a combination of mocks and a Firestore emulator. [cite: 21, 1794, 1808, 1822, 1835, 1845]
* **GCP Emulator Tests (`common_utils/test_gcp_emulator.py` and `tests/app/gcp_emulator_run.py`):**
    * `common_utils/test_gcp_emulator.py`: Unit and integration tests for the `FirestoreEmulator` and `GCSEmulator` classes using Pytest fixtures and context managers. [cite: 128, 134, 1713, 1725]
    * `tests/app/gcp_emulator_run.py`: A script to run Firestore and GCS emulators locally for development and testing purposes, with options to initialize data. [cite: 21, 144] It uses the `gcp_emulator.py` utility. [cite: 144]
* **Configuration**: `pytest.ini` files are present in the root directory, `backend/`, and `whisper_batch/` to configure Pytest behavior for each respective part of the project. [cite: 1, 2, 22, 160, 177, 1855]

## 8. Setup and Running

### 8.1. Environment Configuration

* The application relies heavily on environment variables for configuration.
* Backend: `.env` files in `backend/config/` and `backend/config_develop/` (e.g., `backend/config_develop/.env.develop`). [cite: 7, 525]
* Whisper Batch: `.env` files in `whisper_batch/config/` and `whisper_batch/config_develop/` (e.g., `whisper_batch/config_develop/.env.develop`). [cite: 23, 1925, 1926]
* Frontend: `.env.local` file in `frontend/` for Vite environment variables (e.g., Firebase API keys, API base URL). [cite: 10]

### 8.2. Backend

1.  Set up the required environment variables in `backend/config_develop/.env.develop` or a production `.env` file.
2.  The backend can be run directly using `python -m app.main` (likely after installing dependencies from `backend/requirements.txt`). [cite: 176]
3.  Alternatively, build and run the Docker container defined in `backend/backend_frontend.dockerfile`, which also serves the frontend. [cite: 176] Refer to `gcloud_command例.txt` for deployment examples on Google Cloud Run. [cite: 159]

### 8.3. Frontend

1.  Navigate to the `frontend/` directory. [cite: 9]
2.  Create a `.env.local` file based on `.env.local.sample` and populate it with your Firebase and API configurations. [cite: 10, 1138]
3.  Install dependencies: `npm install` (or `yarn install` / `pnpm install`). [cite: 1127]
4.  Run the development server: `npm run dev`. [cite: 1127]
5.  Build for production: `npm run build`. The output will be in `frontend/dist/`, which is then served by the backend Docker container. [cite: 1127, 176]

### 8.4. Whisper Batch Processor

1.  Set up environment variables in `whisper_batch/config_develop/.env.develop` or a production `.env` file, including `HF_AUTH_TOKEN`. [cite: 1926, 1925]
2.  Build the Docker image using `whisper_batch/whisper_batch.dockerfile`. [cite: 22] Example command: `docker build -t whisper .` [cite: 22]
3.  This component is designed to be run as a GCP Batch job or a standalone worker polling Firestore for jobs. The `main.py` script within `whisper_batch/app/` contains the worker loop. [cite: 23, 1883, 1916]

### 8.5. Local Development with Emulators

* The `tests/app/gcp_emulator_run.py` script can be used to start local Firestore and GCS emulators for development. [cite: 21, 144]
* Ensure Docker is installed and running for the GCS emulator. [cite: 104]
* Set `FIRESTORE_EMULATOR_HOST` and `STORAGE_EMULATOR_HOST` environment variables in your backend/batch applications to point to these local emulators. [cite: 63, 91]

## 9. Utility Scripts

* **`code_printer.py`**: A Python script to print the content of specified files or files within directories, with options for filtering by extension, name, recursion, and omitting files/folders based on gitignore-style patterns. [cite: 1, 25, 26, 33, 34]
* **`tree.py`**: A Python script to display a tree-like structure of a directory, with options to filter by file extension or name, and to exclude certain files/directories. [cite: 1, 161, 163, 164]

## 10. Key Technologies

* **Frontend**: React, Vite, TypeScript, Tailwind CSS, Axios, `pdfjs-dist`, `mammoth`, `xlsx`. [cite: 629, 1127]
* **Backend**: Python, FastAPI, Pydantic, Hypercorn. [cite: 178, 182, 38]
* **Batch Processing**: Python, `faster-whisper`, `pyannote.audio`. [cite: 1856]
* **Authentication**: Firebase Authentication. [cite: 185, 1665]
* **Database**: Firestore (for job queuing, metadata). [cite: 260, 1739]
* **Storage**: Google Cloud Storage (for audio files, transcription results). [cite: 260, 1885]
* **AI Services**: Google Vertex AI (Gemini models for chat, Imagen for image generation), Google Cloud Speech-to-Text. [cite: 385, 471, 475]
* **Mapping**: Google Maps API. [cite: 223, 413]
* **Containerization**: Docker. [cite: 176]
* **Cloud Platform**: Google Cloud Platform (GCP Batch, Cloud Run, Pub/Sub, Speech-to-Text, Maps). [cite: 336, 159]
* **Testing**: Pytest. [cite: 160]