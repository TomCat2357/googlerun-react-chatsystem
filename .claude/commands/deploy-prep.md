本番デプロイの準備を実行してください：

1. **フロントエンドビルド**
   - `cd frontend && npm run build`
   - ビルド結果の確認: `frontend/dist/` ディレクトリの内容確認

2. **Dockerイメージビルドテスト**
   - バックエンド: `docker build -f backend/backend_frontend.dockerfile -t chat-system-test .`
   - バッチ処理: `docker build -f whisper_batch/whisper_batch.dockerfile -t whisper-batch-test .`

3. **本番環境設定の確認**
   - 本番用環境変数の確認
   - Firebase 本番プロジェクト設定の確認
   - GCP 本番プロジェクト設定の確認

4. **セキュリティチェック**
   - 機密情報がコミットされていないか確認
   - CORS設定の確認
   - IPアドレス制限の設定確認

5. **デプロイ前テスト**
   - ローカルでのDockerコンテナ起動テスト
   - エンドポイントの疎通確認

デプロイの準備が完了したら、デプロイ用のコマンド例を提示してください。