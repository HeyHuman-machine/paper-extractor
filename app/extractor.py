"""M3 三级容错抽取器。

把 M1 的纯文本与 M2 的 LLM 客户端连接起来，并把所有预期失败转换成
``ExtractionResult``，为后续批处理提供稳定边界。
"""

from __future__ import annotations

import json
import time
from json import JSONDecodeError
from typing import Any, Protocol

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.evidence import build_evidence_bundle, build_keyword_evidence_bundle
from app.llm import LLMClient, LLMError
from app.models import (
    ExtractionAttempt,
    ExtractionFailure,
    ExtractionResult,
    ExtractionStage,
    LLMResponse,
    PaperRecord,
)
from app.parser import smart_truncate
from app.prompts import (
    append_repair_message,
    build_evidence_extraction_messages,
    build_extraction_messages,
    build_keyword_evidence_extraction_messages,
)


class ChatClient(Protocol):
    """抽取器所需的最小 LLM 接口，测试可注入假客户端。"""

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


class JSONExtractionError(ValueError):
    """模型正文中找不到可用的 JSON 对象。"""


class Extractor:
    """执行 JSON 清洗、Pydantic 校验和修正重试。"""

    def __init__(
        self,
        settings: Settings,
        llm_client: ChatClient,
        *,
        max_repair_retries: int | None = None,
        evidence_aware: bool = False,
        evidence_strategy: str | None = None,
    ) -> None:
        self.settings = settings
        self.llm_client = llm_client
        if max_repair_retries is not None and max_repair_retries < 0:
            raise ValueError("max_repair_retries 不能小于 0")
        self.max_repair_retries = max_repair_retries
        if evidence_strategy not in {None, "sections", "keywords"}:
            raise ValueError("evidence_strategy 仅支持 sections 或 keywords")
        self.evidence_strategy = (
            evidence_strategy or ("sections" if evidence_aware else "none")
        )

    def extract(self, text: str) -> ExtractionResult:
        """从论文文本抽取 ``PaperRecord``，预期失败均作为结果返回。"""

        started_at = time.perf_counter()
        attempts: list[ExtractionAttempt] = []
        total_tokens = 0

        try:
            cleaned_text = text.strip()
            if not cleaned_text:
                raise ValueError("待抽取文本不能为空")
            if self.evidence_strategy == "sections":
                evidence_text = build_evidence_bundle(
                    cleaned_text, self.settings.extract_max_chars
                )
                messages = build_evidence_extraction_messages(evidence_text)
            elif self.evidence_strategy == "keywords":
                evidence_text = build_keyword_evidence_bundle(
                    cleaned_text, self.settings.extract_max_chars
                )
                messages = build_keyword_evidence_extraction_messages(evidence_text)
            else:
                truncated_text = smart_truncate(
                    cleaned_text, self.settings.extract_max_chars
                )
                messages = build_extraction_messages(truncated_text)
        except ValueError as exc:
            return _failure_result(
                stage=ExtractionStage.INPUT,
                error=exc,
                attempts=attempts,
                retry_count=0,
                total_tokens=0,
                started_at=started_at,
            )

        repair_retries = (
            self.settings.llm_max_retries
            if self.max_repair_retries is None
            else self.max_repair_retries
        )
        max_attempts = repair_retries + 1
        last_stage = ExtractionStage.JSON_PARSE
        last_error: Exception = JSONExtractionError("尚未收到模型输出")
        last_raw_output: str | None = None

        for attempt_index in range(max_attempts):
            attempt_number = attempt_index + 1
            try:
                response = self.llm_client.chat(
                    messages, max_tokens=1200, temperature=0.0
                )
            except (LLMError, ValueError) as exc:
                attempts.append(
                    ExtractionAttempt(
                        attempt_number=attempt_number,
                        stage=ExtractionStage.API_ERROR,
                        error_type=type(exc).__name__,
                        error_msg=str(exc),
                    )
                )
                return _failure_result(
                    stage=ExtractionStage.API_ERROR,
                    error=exc,
                    attempts=attempts,
                    retry_count=attempt_index,
                    total_tokens=total_tokens,
                    started_at=started_at,
                )

            total_tokens += response.total_tokens
            raw_output = response.content
            last_raw_output = raw_output

            try:
                parsed_data = parse_json_object(raw_output)
            except JSONExtractionError as exc:
                last_stage = ExtractionStage.JSON_PARSE
                last_error = exc
                attempts.append(
                    _failed_attempt(
                        attempt_number,
                        last_stage,
                        raw_output,
                        exc,
                        response,
                    )
                )
            else:
                try:
                    record = PaperRecord.model_validate(parsed_data)
                except ValidationError as exc:
                    last_stage = ExtractionStage.SCHEMA_VALIDATE
                    last_error = exc
                    attempts.append(
                        _failed_attempt(
                            attempt_number,
                            last_stage,
                            raw_output,
                            exc,
                            response,
                        )
                    )
                else:
                    attempts.append(
                        ExtractionAttempt(
                            attempt_number=attempt_number,
                            stage=ExtractionStage.SUCCESS,
                            raw_output=raw_output,
                            tokens=response.total_tokens,
                            latency_ms=response.latency_ms,
                            transport_retry_count=response.retry_count,
                        )
                    )
                    return ExtractionResult(
                        success=True,
                        record=record,
                        retry_count=attempt_index,
                        total_tokens=total_tokens,
                        total_latency_ms=_elapsed_ms(started_at),
                        attempts=attempts,
                    )

            if attempt_number < max_attempts:
                messages = append_repair_message(
                    messages,
                    raw_output=raw_output,
                    stage=last_stage.value,
                    error_message=_compact_error(last_error),
                )

        return _failure_result(
            stage=last_stage,
            error=last_error,
            attempts=attempts,
            retry_count=max_attempts - 1,
            total_tokens=total_tokens,
            started_at=started_at,
            raw_output=last_raw_output,
        )


def extract(text: str) -> ExtractionResult:
    """规格书要求的简洁入口，负责创建并关闭真实 LLM 客户端。"""

    settings = get_settings()
    with LLMClient(settings=settings) as llm_client:
        return Extractor(settings, llm_client).extract(text)


def parse_json_object(raw_output: str) -> dict[str, Any]:
    """从纯 JSON、Markdown 代码块或前后带废话的正文中提取首个对象。"""

    text = raw_output.strip()
    if not text:
        raise JSONExtractionError("模型返回内容为空")

    decoder = json.JSONDecoder()
    last_error: JSONDecodeError | None = None
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(value, dict):
            return value

    detail = f"：{last_error.msg}" if last_error else ""
    raise JSONExtractionError(f"没有找到可解析的 JSON 对象{detail}")


def _failed_attempt(
    attempt_number: int,
    stage: ExtractionStage,
    raw_output: str,
    error: Exception,
    response: LLMResponse,
) -> ExtractionAttempt:
    return ExtractionAttempt(
        attempt_number=attempt_number,
        stage=stage,
        raw_output=raw_output,
        error_type=type(error).__name__,
        error_msg=_compact_error(error),
        tokens=response.total_tokens,
        latency_ms=response.latency_ms,
        transport_retry_count=response.retry_count,
    )


def _failure_result(
    stage: ExtractionStage,
    error: Exception,
    attempts: list[ExtractionAttempt],
    retry_count: int,
    total_tokens: int,
    started_at: float,
    raw_output: str | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        success=False,
        failure=ExtractionFailure(
            stage=stage,
            error_type=type(error).__name__,
            error_msg=_compact_error(error),
            raw_llm_output=raw_output,
        ),
        retry_count=retry_count,
        total_tokens=total_tokens,
        total_latency_ms=_elapsed_ms(started_at),
        attempts=attempts,
    )


def _compact_error(error: Exception, max_chars: int = 1500) -> str:
    """限制错误文本长度，保留足够信息供模型修正和界面诊断。"""

    message = str(error).strip() or type(error).__name__
    return message[:max_chars]


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
