開発環境セットアップを実行してください：

1. **環境変数ファイル確認**
   - `backend/config/.env.sample` から `.env` ファイルを作成済みか確認
   - `frontend/.env.local.sample` から `.env.local` ファイルを作成済みか確認
   - `whisper_batch/config/.env.sample` から `.env` ファイルを作成済みか確認

2. **依存関係インストール**
   - バックエンド: `cd backend && pip install -r requirements.txt`
   - フロントエンド: `cd frontend && npm install`

3. **Firebase設定確認**
   - Firebase プロジェクトの設定完了確認
   - サービスアカウントキーファイルの配置確認

4. **Google Cloud設定確認**
   - GCP プロジェクトの設定確認
   - 必要なAPIの有効化確認（Vertex AI, Speech-to-Text, Maps API等）

5. **開発サーバー起動**
   - GCPエミュレータ: `python tests/app/gcp_emulator_run.py`
   - バックエンド: `cd backend && python -m app.main`
   - フロントエンド: `cd frontend && npm run dev`

上記の手順を順番に実行し、問題があれば報告してください。