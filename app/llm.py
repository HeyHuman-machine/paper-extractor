"""使用 httpx 手写的 OpenAI 兼容 LLM 客户端。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.models import LLMResponse


Message = dict[str, str]


class LLMError(RuntimeError):
    """所有大模型调用错误的基类。"""


class LLMAuthenticationError(LLMError):
    """API Key 无效或无权访问模型。"""


class LLMRequestError(LLMError):
    """请求参数有误，不应盲目重试。"""


class LLMRetryExhaustedError(LLMError):
    """可重试错误在达到上限后仍未恢复。"""


class LLMResponseError(LLMError):
    """服务响应成功，但缺少项目需要的数据。"""


class LLMClient:
    """可注入 HTTP 客户端和等待函数，方便零费用自动测试。"""

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client(
            timeout=self.settings.llm_timeout
        )
        self.sleep_fn = sleep_fn

    def close(self) -> None:
        """只关闭由本对象创建的 HTTP 客户端。"""

        if self._owns_client:
            self.http_client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def chat(
        self,
        messages: list[Message],
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """发送对话请求，并对超时、429 和 5xx 做指数退避重试。"""

        if not messages:
            raise ValueError("messages 不能为空")
        if max_tokens <= 0:
            raise ValueError("max_tokens 必须大于 0")

        payload = self._build_payload(messages, max_tokens, temperature)
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.settings.llm_base_url}/chat/completions"
        started_at = time.perf_counter()

        for attempt in range(self.settings.llm_max_retries + 1):
            try:
                response = self.http_client.post(
                    endpoint, headers=headers, json=payload
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.settings.llm_max_retries:
                    raise LLMRetryExhaustedError(
                        f"LLM 网络错误，重试 {attempt} 次后仍失败：{type(exc).__name__}"
                    ) from exc
                self._wait_before_retry(attempt)
                continue

            if response.status_code in {401, 403}:
                raise LLMAuthenticationError(
                    "DeepSeek 身份验证失败，请检查 API Key 和模型权限"
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.settings.llm_max_retries:
                    raise LLMRetryExhaustedError(
                        f"LLM 服务返回 HTTP {response.status_code}，"
                        f"重试 {attempt} 次后仍失败"
                    )
                self._wait_before_retry(attempt)
                continue
            if response.is_error:
                raise LLMRequestError(
                    f"LLM 请求失败，HTTP {response.status_code}："
                    f"{_safe_error_message(response)}"
                )

            latency_ms = round((time.perf_counter() - started_at) * 1000)
            return self._parse_response(response, latency_ms, attempt)

        raise AssertionError("重试循环不应运行到这里")

    def _build_payload(
        self,
        messages: list[Message],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """构造请求体，明确控制 thinking 和 JSON Output。"""

        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "thinking": {
                "type": "enabled"
                if self.settings.llm_thinking_enabled
                else "disabled"
            },
        }
        if self.settings.llm_json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _wait_before_retry(self, attempt: int) -> None:
        """第1次等1秒、第2次等2秒，避免立刻反复撞击故障服务。"""

        self.sleep_fn(float(2**attempt))

    def _parse_response(
        self, response: httpx.Response, latency_ms: int, retry_count: int
    ) -> LLMResponse:
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("LLM 响应结构不完整，无法读取正文") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("LLM 返回了空正文")

        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or prompt_tokens + completion_tokens
        )
        return LLMResponse(
            content=content,
            model=str(data.get("model") or self.settings.llm_model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            retry_count=retry_count,
        )


def chat(
    messages: list[Message],
    max_tokens: int = 1200,
    temperature: float = 0.0,
) -> LLMResponse:
    """规格书要求的简洁调用入口。"""

    with LLMClient() as client:
        return client.chat(messages, max_tokens, temperature)


def _safe_error_message(response: httpx.Response) -> str:
    """提取服务端错误摘要，但绝不包含请求头中的 API Key。"""

    try:
        data = response.json()
    except ValueError:
        return response.text[:300] or "无错误正文"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
    return str(data)[:300]
