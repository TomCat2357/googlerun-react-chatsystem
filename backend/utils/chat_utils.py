# utils/chat_utils.py
from typing import List
from litellm import completion
from utils.common import get_api_key_for_model

def common_message_function(*, model: str, messages: List, stream: bool = False, **kwargs):
    """
    LiteLLM経由でチャットメッセージを送信し応答を取得する
    """
    if stream:
        def chat_stream():
            for i, text in enumerate(
                completion(messages=messages, model=model, stream=True, **kwargs)
            ):
                if not i:
                    yield
                yield text["choices"][0]["delta"].get("content", "") or ""

        cs = chat_stream()
        cs.__next__()
        return cs
    else:
        return completion(messages=messages, model=model, stream=False, **kwargs)[
            "choices"
        ][0]["message"]["content"]