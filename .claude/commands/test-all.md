プロジェクト全体のテストを実行してください：

1. **事前確認**
   - GCPエミュレータが起動していることを確認
   - 環境変数が正しく設定されていることを確認

2. **テスト実行**
   - バックエンドのテスト: `cd backend && pytest -v`
   - Whisperバッチのテスト: `cd whisper_batch && pytest -v`  
   - 共通ユーティリティのテスト: `cd common_utils && pytest -v`
   - 統合テスト: `cd tests && pytest -v`

3. **フロントエンドチェック**
   - リント: `cd frontend && npm run lint`
   - ビルド確認: `cd frontend && npm run build`

4. **結果レポート**
   - テスト結果をまとめて報告
   - 失敗したテストがあれば詳細な調査と修正提案

すべてのテストが通るまで実行し、問題があれば修正してください。