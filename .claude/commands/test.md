プロジェクトのテストを実行・管理してください：

## 基本テスト実行

```bash
# 全体テスト（推奨オプション付き）
pytest -vv --tb=short -s

# バックエンドのみ
cd backend && pytest

# 特定テストファイル
pytest tests/app/test_specific.py

# 特定テスト関数
pytest tests/app/test_file.py::test_function_name

# パターンマッチ実行
pytest -k "whisper" -v  # whisperを含むテスト名のみ実行
```

## 開発時のテスト戦略

### 1. デバッグテスト
```bash
# 失敗時デバッガ起動
pytest --pdb

# 特定テストをデバッグ
pytest tests/app/test_specific.py::test_function --pdb

# ブレークポイント設定（コード内）
def test_something():
    setup_data()
    breakpoint()  # ここで一時停止
    result = function_under_test()
    assert result.status == "success"
```

### 2. 効率的なテスト実行
```bash
# 並列実行（pytest-xdist使用時）
pytest -n auto

# 失敗テストのみ再実行
pytest --lf

# 最初の失敗で停止
pytest -x

# カスタムマーカーで絞り込み
pytest -m "not slow"  # slowマーカー以外を実行
```

### 3. テスト作成ガイドライン

#### 命名規約
```python
# 良い例：仕様を明確に記載
def test_whisper_api_音声ファイルが正常な場合文字起こし結果を返すこと():
    pass

def test_chat_api_無効なトークンの場合401エラーを返すこと():
    pass

# 避ける例：仕様が不明確
def test_whisper_正常系():
    pass
```

#### パラメータテスト
```python
@pytest.mark.parametrize(
    ["input_file", "expected_format"],
    [
        ("test.wav", "wav"),
        ("test.mp3", "mp3"), 
        ("test.m4a", "m4a"),
    ],
    ids=[
        "WAVファイル形式の場合",
        "MP3ファイル形式の場合", 
        "M4Aファイル形式の場合",
    ],
)
def test_audio_format_detection_各形式で正しく検出されること(input_file, expected_format):
    result = detect_audio_format(input_file)
    assert result == expected_format
```

## テスト環境セットアップ

### 1. 仮想環境とテスト要件
```bash
# 仮想環境アクティベート
source .venv/bin/activate

# テスト用ライブラリインストール
/root/.local/bin/uv pip install -r tests/requirements.txt
```

### 2. GCPエミュレータ起動
```bash
# テスト前にエミュレータ起動
python tests/app/gcp_emulator_run.py
```

### 3. 環境変数設定
```bash
# デバッグモード
export DEBUG=1

# テスト環境識別
export ENVIRONMENT=test
```

## テスト結果の分析

### 1. カバレッジ測定
```bash
# カバレッジ測定
pytest --cov=backend/app --cov-report=html

# カバレッジ結果確認
open htmlcov/index.html
```

### 2. テスト出力解析
```bash
# 詳細出力
pytest -vv

# JUnit XML出力（CI用）
pytest --junitxml=test-results.xml

# 最遅テストの特定
pytest --durations=10
```

### 3. 失敗の対処
```bash
# 失敗詳細確認
pytest --tb=long

# 標準出力表示
pytest -s

# 警告表示
pytest -W ignore::DeprecationWarning
```

## トラブルシューティング

**テスト失敗時**:
1. `pytest --pdb` でデバッガ起動
2. ログレベルを `DEBUG=1` で詳細化
3. `breakpoint()` でブレークポイント設定

**環境問題**:
1. 仮想環境のアクティベート確認
2. 依存関係の再インストール
3. GCPエミュレータの状態確認

**パフォーマンス**:
1. `pytest --durations=10` で遅いテスト特定
2. 重いテストに `@pytest.mark.slow` マーカー付与
3. `pytest -m "not slow"` で高速テストのみ実行