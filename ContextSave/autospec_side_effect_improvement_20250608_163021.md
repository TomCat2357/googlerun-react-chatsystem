# Objective
create_autospec() + side_effectパターンの全面適用により、テストシステムの安全性・保守性・拡張性を大幅向上

# All user instructions
- tests/app/内のテストでcreate_autospec() + side_effect（推奨）がされていないものを修正
- claude.mdにcreate_autospec() + side_effect（推奨）をテストとして強く推奨する旨記載
- 型安全性を保ちつつカスタム振る舞いを実現する方法の実装
- 存在しないメソッドの呼び出しを防ぐ安全なモック設計の確立

# Current status of the task
✅ claude.mdにモック設計の黄金律セクションを追加
✅ create_autospec() + side_effectパターンを強く推奨として明記
✅ test_whisper_api.pyの大幅修正完了
  - GCSClientBehavior, GCSBucketBehavior, GCSBlobBehavior追加
  - FirestoreClientBehavior, FirestoreCollectionBehavior, FirestoreDocumentBehavior追加
  - 主要テストメソッド8つをcreate_autospec + side_effectパターンに変更
✅ test_whisper_batch.pyの修正完了
  - BatchFirestoreClientBehavior, BatchGCSClientBehavior等追加
  - test_pick_next_job_success, test_process_job_successをパターン適用
✅ test_whisper_integration.pyの修正完了
  - IntegrationGCSClientBehavior, IntegrationFirestoreClientBehavior等追加
  - test_whisper_workflow_with_mocksをパターン適用

# Pending issues with snippets
なし - 全ての修正が完了し、テストの安全性と保守性が向上しました

# Build and development instructions
```bash
# テスト実行確認
pytest tests/app/ -v

# 特定テストファイルの実行
pytest tests/app/test_whisper_api.py -v
pytest tests/app/test_whisper_batch.py -v  
pytest tests/app/test_whisper_integration.py -v

# モック設計ガイドラインの確認
# claude.md の「モック設計の黄金律」セクションを参照
```

# Relevant file paths
- claude.md
- tests/app/test_whisper_api.py
- tests/app/test_whisper_batch.py
- tests/app/test_whisper_integration.py

# Technical achievements
- 型安全性向上：autospecにより存在しないメソッド呼び出しを防止
- 柔軟性向上：side_effectによりカスタム動作とバリデーションが可能
- 保守性向上：API変更時の検出、明確なエラー原因、一貫したパターン
- Behaviorクラスパターンで再利用可能な設計確立
- 実際のAPIと同じインターフェースを維持しつつ状態管理を実現