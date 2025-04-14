# テスト実行手順

このディレクトリには、プロジェクトのテストコードが含まれています。

## テストの実行方法

### 仮想環境の準備

テストを実行する前に、whisper_queueディレクトリの仮想環境をアクティベートします：

```bash
# whisper_queue仮想環境をアクティベート
source whisper_queue/.venv/bin/activate
```

### テスト実行

すべてのテストを実行する場合：

```bash
python -m pytest
```

特定のテストファイルを実行する場合：

```bash
python -m pytest tests/unit/test_whisper_queue.py
```

詳細な出力でテストを実行する場合：

```bash
python -m pytest -v tests/unit/test_whisper_queue.py
```

テスト結果のレポートを生成する場合：

```bash
python -m pytest --html=report.html
```

### テストマーカーの利用

特定のカテゴリのテストのみを実行する場合は、マーカーを使用します：

```bash
# 単体テストのみを実行
python -m pytest -m unit

# Whisper関連のテストのみを実行
python -m pytest -m whisper
```

## トラブルシューティング

テスト実行中にエラーが発生した場合は、以下を確認してください：

1. 仮想環境がアクティベートされていることを確認
2. 必要なパッケージがインストールされていることを確認（`pip install -r whisper_queue/config/requirement.txt`）
3. テスト用の環境変数が正しく設定されていることを確認
4. テストファイルの構文エラーがないことを確認

## テストの追加方法

新しいテストを追加する場合は、以下のガイドラインに従ってください：

1. テストファイルは `tests/unit/` または `tests/integration/` ディレクトリに配置
2. テストファイル名は `test_` で始める（例：`test_speech_service.py`）
3. テスト関数名も `test_` で始める（例：`test_process_audio()`）
4. 適切なマーカーを使用してテストを分類する
