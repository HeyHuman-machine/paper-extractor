"""M2 HTTP 客户端关键行为测试，不访问真实网络。"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.llm import (
    LLMAuthenticationError,
    LLMClient,
    LLMRequestError,
    LLMResponseError,
    LLMRetryExhaustedError,
)


MESSAGES = [
    {"role": "system", "content": "只输出 JSON"},
    {"role": "user", "content": "extract this paper"},
]


def settings(max_retries: int = 2) -> Settings:
    """构造完全虚假的测试配置。"""

    return Settings.from_env(
        {
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": "https://api.deepseek.com/v1",
            "LLM_MODEL": "deepseek-v4-flash",
            "LLM_API_KEY": "test-key-not-real",
            "LLM_TIMEOUT": "60",
            "LLM_MAX_RETRIES": str(max_retries),
            "LLM_THINKING_ENABLED": "false",
            "LLM_JSON_MODE": "true",
            "EXTRACT_MAX_CHARS": "12000",
            "BATCH_CONCURRENCY": "3",
        }
    )


def success_json() -> dict[str, Any]:
    return {
        "model": "deepseek-v4-flash",
        "choices": [{"message": {"content": '{"title":"Demo"}'}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        },
    }


def client_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 2,
    sleeps: list[float] | None = None,
) -> LLMClient:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMClient(
        settings(max_retries),
        http_client=http_client,
        sleep_fn=(sleeps.append if sleeps is not None else lambda _: None),
    )


def test_success_records_usage_and_request_controls() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json=success_json())

    result = client_with_handler(handler).chat(MESSAGES, max_tokens=900)

    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key-not-real"
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["max_tokens"] == 900
    assert result.content == '{"title":"Demo"}'
    assert result.total_tokens == 120
    assert result.retry_count == 0


def test_429_retries_with_exponential_backoff() -> None:
    call_count = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(429, json={"error": {"message": "busy"}})
        return httpx.Response(200, json=success_json())

    result = client_with_handler(handler, sleeps=sleeps).chat(MESSAGES)

    assert call_count == 3
    assert sleeps == [1.0, 2.0]
    assert result.retry_count == 2


def test_timeout_retries_then_succeeds() -> None:
    call_count = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json=success_json())

    result = client_with_handler(handler, sleeps=sleeps).chat(MESSAGES)

    assert call_count == 2
    assert sleeps == [1.0]
    assert result.retry_count == 1


def test_500_exhausts_retry_limit() -> None:
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503, json={"error": {"message": "down"}})

    with pytest.raises(LLMRetryExhaustedError, match="HTTP 503"):
        client_with_handler(handler, max_retries=1).chat(MESSAGES)

    assert call_count == 2


def test_authentication_error_does_not_retry() -> None:
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(LLMAuthenticationError, match="身份验证"):
        client_with_handler(handler).chat(MESSAGES)

    assert call_count == 1


def test_other_4xx_does_not_retry() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad payload"}})

    with pytest.raises(LLMRequestError, match="bad payload"):
        client_with_handler(handler).chat(MESSAGES)


def test_empty_content_has_friendly_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        data = success_json()
        data["choices"][0]["message"]["content"] = ""
        return httpx.Response(200, json=data)

    with pytest.raises(LLMResponseError, match="空正文"):
        client_with_handler(handler).chat(MESSAGES)
