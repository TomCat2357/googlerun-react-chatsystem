プロジェクトのテストを実行・管理してください：

## ユニットテストの基本原則

### 「1単位の振る舞い」の識別
テストを書く前に、何をテストすべきかを明確にしましょう：

```python
# ❌ 悪い例：大きすぎる振る舞い
def test_complete_chat_flow_全処理():
    """認証→メッセージ送信→AI応答→保存の全工程をテスト"""
    # この場合、因子が多すぎてテスト設計が困難
    pass

# ✅ 良い例：分割された振る舞い
class TestMessageValidation:
    """メッセージ検証の振る舞い"""
    def test_validate_message_正常なメッセージで成功(self):
        pass
    
    def test_validate_message_空文字でValidationError(self):
        pass

class TestAIResponseGeneration:
    """AI応答生成の振る舞い"""
    def test_generate_response_正常なプロンプトで応答生成(self):
        pass
```

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

## テストコードのSOS原則実践

### S - 構造化されている（Structured）

#### 階層化されたテストクラス
```python
class TestWhisperAPI:
    """Whisper API のテスト"""
    
    class TestNormalCases:
        """正常系テスト"""
        
        def test_process_audio_有効なWAVファイルで文字起こし成功(self):
            # Arrange
            audio_file = "tests/data/sample.wav"
            
            # Act
            result = whisper_api.process_audio(audio_file)
            
            # Assert
            assert result.success is True
            assert result.transcription is not None
    
    class TestErrorCases:
        """異常系テスト"""
        
        def test_process_audio_無効なファイル形式で400エラー(self):
            pass
    
    class TestEdgeCases:
        """境界値・エッジケーステスト"""
        
        def test_process_audio_最大ファイルサイズ_100MB_で正常処理(self):
            pass
```

### O - 整理されている（Organized）

#### テスト設計の根拠を明記
```python
class TestAudioFormatValidation:
    """
    音声ファイル形式検証のテスト
    
    テスト設計の根拠：
    - 同値分割：有効形式（wav, mp3, m4a）vs 無効形式（txt, jpg等）
    - 境界値分析：ファイルサイズ上限（100MB）付近
    - エラー推測：拡張子と実際の形式が異なるケース
    """
    
    @pytest.mark.parametrize(
        ["file_format", "file_size_mb", "expected_valid"],
        [
            ("wav", 50, True),      # 正常：有効形式・通常サイズ
            ("mp3", 99, True),      # 境界値：上限付近
            ("m4a", 101, False),    # 境界値：上限超過
            ("txt", 10, False),     # エラー：無効形式
        ],
        ids=[
            "WAV_50MB_有効",
            "MP3_99MB_境界値内",
            "M4A_101MB_境界値超過",
            "TXT_10MB_無効形式",
        ],
    )
    def test_validate_audio_file_各条件の検証結果が正しいこと(
        self, file_format, file_size_mb, expected_valid
    ):
        pass
```

### D - 自己文書化されている（Self-documenting）

#### AAA パターンの徹底
```python
def test_whisper_batch_job_正常なパラメータで処理開始されること(self):
    """Whisperバッチジョブが正常なパラメータで開始されることを検証"""
    # Arrange（準備）
    audio_file_path = "gs://bucket/test_audio.wav"
    job_config = WhisperJobConfig(
        language="ja",
        speaker_diarization=True,
        model="large-v3"
    )
    
    # Act（実行）- 原則1文
    result = whisper_service.start_batch_job(audio_file_path, job_config)
    
    # Assert（検証）
    assert result.status == "SUBMITTED"
    assert result.job_id is not None
    assert result.estimated_completion_time > datetime.now()
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

#### 命名規約：条件と期待する振る舞いを明示
```python
# ✅ 良い例：条件と期待する振る舞いが明確
def test_whisper_api_音声ファイルが正常な場合文字起こし結果を返すこと():
    pass

def test_chat_api_無効なトークンの場合401エラーを返すこと():
    pass

def test_calculate_movie_ticket_price_大人平日_通常料金2000円を返すこと():
    pass

# ❌ 避ける例：仕様が不明確
def test_whisper_正常系():
    pass

def test_whisper_api():
    pass
```

#### テストダブルの利用指針

**基本方針（優先順位）：**
1. **まず、テストダブルを使わずに済むか考える**
2. **スタブは目的を理解した上で適切に使えばOK**
3. **モックの利用は極めて慎重に**

```python
# ✅ 最優先：テストダブルなしでテスト
def test_price_calculator_通常料金計算_テストダブルなし(self):
    calculator = PriceCalculator()
    result = calculator.calculate_regular_price(CustomerType.ADULT)
    assert result == 2000

# ✅ 必要に応じてスタブ使用（間接入力の制御）
def test_currency_converter_為替APIエラー時デフォルトレート使用(self):
    # 外部API呼び出しをスタブで制御
    with patch('external_api.get_exchange_rate') as stub_api:
        stub_api.side_effect = ConnectionError("API接続エラー")
        
        result = currency_converter.convert(100, 'USD', 'JPY')
        assert result == 11000  # デフォルトレート適用

# ⚠️ 慎重に使用：モック（間接出力の観測）
def test_notification_service_メール送信が実行されること(self):
    """
    注意：以下を事前に検討済み
    - それは本当に観測すべきものか？
    - 副作用がなくなるように設計を見直せないか？
    """
    with patch('email_service.send_email') as mock_email:
        notification_service.notify_user("user@example.com", "メッセージ")
        
        # 外部との契約として観察可能な振る舞いのみ検証
        mock_email.assert_called_once_with(
            to="user@example.com",
            subject="通知",
            body="メッセージ"
        )
```

#### いつスタブを使うか
```python
# ✅ 適切なスタブ使用例
def test_audio_processing_ファイル読み込みエラー時の処理(self):
    """制御困難なファイルI/Oエラーをスタブで再現"""
    with patch('builtins.open', side_effect=IOError("ファイルが見つかりません")):
        result = audio_processor.process_file("nonexistent.wav")
        assert result.error == "FILE_NOT_FOUND"

def test_whisper_api_外部サービス障害時の動作(self):
    """通常だと発生しない例外をスタブで発生"""
    with patch('whisper_client.transcribe') as stub_whisper:
        stub_whisper.side_effect = TimeoutError("サービスタイムアウト")
        
        result = whisper_service.process_audio("test.wav")
        assert result.status == "TIMEOUT_ERROR"
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