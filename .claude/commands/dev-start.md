開発環境を起動してください：

1. **GCP エミュレータ起動**
   ```bash
   python tests/app/gcp_emulator_run.py
   ```

2. **バックエンド起動**  
   ```bash
   cd backend && python -m app.main
   ```

3. **フロントエンド起動**
   ```bash
   cd frontend && npm run dev
   ```

起動完了後、ブラウザで http://localhost:5173 にアクセスして動作確認してください。