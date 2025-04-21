import pytest
import asyncio
from common_utils.logger import sanitize_request_data, create_dict_logger, wrap_asyncgenerator_logger, logger

def test_sanitize_truncate_string():
    # 長い文字列が指定長を超えると末尾に [TRUNCATED] が付き、最大長まで切り詰められる
    long_str = "x" * 100
    result = sanitize_request_data(long_str, max_length=10)
    assert isinstance(result, str)
    assert result.endswith("[TRUNCATED]")
    # "[TRUNCATED]" を含めた長さが max_length + len("[TRUNCATED]") になる
    assert len(result) == 10 + len("[TRUNCATED]")

def test_sanitize_redact_sensitive():
    # キーに敏感ワードが含まれる場合は値が [REDACTED] になる
    data = {"password": "secret", "nested": {"user_password": "pa", "ok": "fine"}}
    result = sanitize_request_data(data, max_length=None, sensitive_keys=["password"])
    assert result["password"] == "[REDACTED]"
    assert result["nested"]["user_password"] == "[REDACTED]"
    assert result["nested"]["ok"] == "fine"

def test_create_dict_logger_logs_and_returns_dict(monkeypatch):
    # logger.info が呼ばれ、機密情報はマスクされる
    called = {}
    def fake_info(msg):
        called['msg'] = msg
    monkeypatch.setattr(logger, 'info', fake_info)
    input_dict = {'key': 'value', 'password': 'secret'}
    result = create_dict_logger(input_dict, meta_info={'a':1}, max_length=None, sensitive_keys=['password'])
    # 入力辞書がそのまま返る
    assert result == input_dict
    # ログに出力された辞書に meta_info とマスク済みのキーが含まれる
    assert called['msg']['a'] == 1
    assert called['msg']['password'] == '[REDACTED]'

@pytest.mark.asyncio
async def test_wrap_asyncgenerator_logger(monkeypatch):
    # 非同期ジェネレータをログ出力付きにラップし、元のチャンクが返ることを確認
    chunks = ['chunk1', 'chunk2', 'long_chunk'] # 'chunk1' is 6 chars, 'long_chunk' is 10 chars
    async def gen():
        for c in chunks:
            yield c
    # fake logger
    logs = []
    def fake_info(msg):
        logs.append(msg)
    monkeypatch.setattr(logger, 'info', fake_info)

    max_len = 5
    decorator = wrap_asyncgenerator_logger(meta_info={'x':2}, max_length=max_len)
    wrapped_gen = decorator(gen)

    # ラップ後のジェネレータを実行し、結果とログを検証
    result = []
    async for item in wrapped_gen():
        result.append(item)
    assert result == chunks
    # 各チャンクごとにログ出力が行われ、'chunk' フィールドにトリミングされたチャンク文字列が入る
    assert len(logs) == len(chunks)
    for msg, orig in zip(logs, chunks):
        assert msg['x'] == 2
        # sanitize_request_dataのロジックに合わせて期待値を生成して比較
        expected_chunk_log = sanitize_request_data(orig, max_length=max_len)
        assert msg['chunk'] == expected_chunk_log, f"ログのチャンク '{msg['chunk']}' が期待値 '{expected_chunk_log}' と異なります (元: '{orig}')"
