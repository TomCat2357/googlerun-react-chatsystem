音声処理関連の問題を修正してください：

問題: $ARGUMENTS

1. **音声ファイル関連の診断**
   - ファイル形式の確認（対応形式: wav, mp3, m4a, flac等）
   - ファイルサイズの確認（制限: `MAX_PAYLOAD_SIZE`）
   - 音声時間の確認（制限: `SPEECH_MAX_SECONDS`）

2. **バックエンド確認**
   - `backend/app/api/speech.py` の実装確認
   - `backend/app/api/whisper.py` の実装確認
   - `backend/app/core/audio_utils.py` の音声処理ユーティリティ確認

3. **バッチ処理確認**
   - `whisper_batch/app/main.py` の処理ロジック確認
   - `whisper_batch/app/transcribe.py` のTranscription処理確認
   - `whisper_batch/app/diarize.py` の話者分離処理確認

4. **環境依存の確認**
   - ffmpeg のインストール確認
   - CUDA環境の確認（GPU使用時）
   - HuggingFace認証トークンの確認

5. **ログ解析**
   - バックエンドログの確認
   - バッチ処理ログの確認
   - GCP Batch ジョブログの確認

問題を特定し、適切な修正を実装してください。必要に応じてテストケースも追加してください。