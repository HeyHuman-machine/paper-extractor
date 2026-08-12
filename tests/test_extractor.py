"""M3 三级容错抽取器测试，所有模型响应均为本地模拟。"""

from __future__ import annotations

import json
from collections.abc import Iterable

from app.config import Settings
from app.extractor import Extractor, parse_json_object
from app.llm import LLMRequestError
from app.models import ExtractionStage, LLMResponse
from app.prompts import FEW_SHOT_RESULT


def settings(max_retries: int = 2) -> Settings:
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


def response(content: str, tokens: int = 100, latency_ms: int = 20) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="deepseek-v4-flash",
        prompt_tokens=tokens - 20,
        completion_tokens=20,
        total_tokens=tokens,
        latency_ms=latency_ms,
        retry_count=0,
    )


class FakeLLMClient:
    """按顺序返回预设响应或抛出预设异常，并保存收到的消息。"""

    def __init__(self, outcomes: Iterable[LLMResponse | Exception]) -> None:
        self.outcomes = iter(outcomes)
        self.received_messages: list[list[dict[str, str]]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.received_messages.append(messages)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def valid_json(**changes: object) -> str:
    data = {**FEW_SHOT_RESULT, **changes}
    return json.dumps(data, ensure_ascii=False)


def test_normal_response_succeeds_without_retry() -> None:
    client = FakeLLMClient([response(valid_json())])

    result = Extractor(settings(), client).extract("a fictional paper")

    assert result.success is True
    assert result.record is not None
    assert result.record.title == FEW_SHOT_RESULT["title"]
    assert result.retry_count == 0
    assert result.total_tokens == 100
    assert [attempt.stage for attempt in result.attempts] == [
        ExtractionStage.SUCCESS
    ]


def test_parser_strips_code_fence_and_extra_text() -> None:
    raw_output = f"这是结果：\n```json\n{valid_json()}\n```\n处理完成"

    parsed = parse_json_object(raw_output)

    assert parsed["title"] == FEW_SHOT_RESULT["title"]
    assert len(parsed) == 11


def test_non_json_triggers_repair_then_succeeds() -> None:
    client = FakeLLMClient(
        [response("I cannot produce JSON", 60), response(valid_json(), 90)]
    )

    result = Extractor(settings(), client).extract("a fictional paper")

    assert result.success is True
    assert result.retry_count == 1
    assert result.total_tokens == 150
    assert [attempt.stage for attempt in result.attempts] == [
        ExtractionStage.JSON_PARSE,
        ExtractionStage.SUCCESS,
    ]
    repair_message = client.received_messages[1][-1]["content"]
    assert "失败阶段：json_parse" in repair_message
    assert "没有找到可解析的 JSON 对象" in repair_message


def test_missing_title_triggers_schema_repair_then_succeeds() -> None:
    invalid_data = {**FEW_SHOT_RESULT}
    invalid_data.pop("title")
    client = FakeLLMClient(
        [
            response(json.dumps(invalid_data, ensure_ascii=False), 70),
            response(valid_json(), 80),
        ]
    )

    result = Extractor(settings(), client).extract("a fictional paper")

    assert result.success is True
    assert result.retry_count == 1
    assert result.attempts[0].stage == ExtractionStage.SCHEMA_VALIDATE
    assert result.attempts[0].error_type == "ValidationError"
    repair_message = client.received_messages[1][-1]["content"]
    assert "失败阶段：schema_validate" in repair_message
    assert "title" in repair_message


def test_retry_exhaustion_returns_failure_instead_of_raising() -> None:
    client = FakeLLMClient(
        [response("not json", 40), response("still not json", 50)]
    )

    result = Extractor(settings(max_retries=1), client).extract(
        "a fictional paper"
    )

    assert result.success is False
    assert result.record is None
    assert result.failure is not None
    assert result.failure.stage == ExtractionStage.JSON_PARSE
    assert result.failure.raw_llm_output == "still not json"
    assert result.retry_count == 1
    assert result.total_tokens == 90
    assert len(result.attempts) == 2


def test_api_error_is_isolated_as_failure_result() -> None:
    client = FakeLLMClient([LLMRequestError("bad request")])

    result = Extractor(settings(), client).extract("a fictional paper")

    assert result.success is False
    assert result.failure is not None
    assert result.failure.stage == ExtractionStage.API_ERROR
    assert result.failure.error_type == "LLMRequestError"
    assert result.retry_count == 0
    assert result.attempts[0].stage == ExtractionStage.API_ERROR


def test_blank_input_isolated_without_calling_llm() -> None:
    client = FakeLLMClient([])

    result = Extractor(settings(), client).extract("   ")

    assert result.success is False
    assert result.failure is not None
    assert result.failure.stage == ExtractionStage.INPUT
    assert result.attempts == []
    assert client.received_messages == []


def test_all_schema_attempts_fail_with_last_diagnostic() -> None:
    invalid_data = {**FEW_SHOT_RESULT, "year": 1949}
    invalid_json = json.dumps(invalid_data, ensure_ascii=False)
    client = FakeLLMClient(
        [response(invalid_json, 50), response(invalid_json, 60)]
    )

    result = Extractor(settings(max_retries=1), client).extract(
        "a fictional paper"
    )

    assert result.success is False
    assert result.failure is not None
    assert result.failure.stage == ExtractionStage.SCHEMA_VALIDATE
    assert "year" in result.failure.error_msg
    assert result.total_tokens == 110
    assert all(
        attempt.stage == ExtractionStage.SCHEMA_VALIDATE
        for attempt in result.attempts
    )
