音声処理の問題を調査・修正してください：

**問題**: $ARGUMENTS

**調査項目**:
1. ファイル形式・サイズ・時間制限の確認
2. `backend/app/api/speech.py`, `whisper.py` の確認  
3. `whisper_batch/app/` 配下の処理ロジック確認
4. ffmpeg, CUDA, HuggingFace トークンの環境確認
5. ログ（バックエンド、バッチ処理、GCP Batch）の解析

問題を特定して修正を実装し、必要に応じてテストを追加してください。