"""V6 主结果精修：只调用模型重抽 ``main_results``，不修改其余十个字段。"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.evidence import build_keyword_evidence_bundle
from app.extractor import JSONExtractionError, parse_json_object
from app.llm import LLMError
from app.models import LLMResponse
from app.prompts import build_result_refinement_messages


class ResultRefinementPayload(BaseModel):
    """结果专用调用唯一允许返回的 JSON 结构。"""

    main_results: list[str] = Field(default_factory=list)

    @field_validator("main_results")
    @classmethod
    def normalize_results(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized


@dataclass(frozen=True, slots=True)
class ResultRefinement:
    """单论文结果精修的可观测返回值。"""

    success: bool
    main_results: list[str] | None
    tokens: int
    latency_ms: int
    retry_count: int
    error: str | None = None


class ResultRefiner:
    """从关键词证据中重抽结果，失败时由调用方回退到原记录。"""

    def __init__(self, llm_client: object, *, max_retries: int = 2) -> None:
        if max_retries < 0:
            raise ValueError("max_retries 不能小于 0")
        self.llm_client = llm_client
        self.max_retries = max_retries

    def refine(self, text: str, max_chars: int) -> ResultRefinement:
        started_at = time.perf_counter()
        try:
            evidence = build_keyword_evidence_bundle(text, max_chars)
            messages = build_result_refinement_messages(evidence)
        except ValueError as exc:
            return _failed_refinement(exc, started_at)

        total_tokens = 0
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response: LLMResponse = self.llm_client.chat(
                    messages, max_tokens=700, temperature=0.0
                )
                total_tokens += response.total_tokens
                payload = ResultRefinementPayload.model_validate(
                    parse_json_object(response.content)
                )
                return ResultRefinement(
                    success=True,
                    main_results=payload.main_results,
                    tokens=total_tokens,
                    latency_ms=_elapsed_ms(started_at),
                    retry_count=attempt,
                )
            except (LLMError, ValueError, JSONExtractionError, ValidationError) as exc:
                last_error = exc

        return ResultRefinement(
            success=False,
            main_results=None,
            tokens=total_tokens,
            latency_ms=_elapsed_ms(started_at),
            retry_count=self.max_retries,
            error=str(last_error)[:800] if last_error else "结果精修失败",
        )


def _failed_refinement(error: Exception, started_at: float) -> ResultRefinement:
    return ResultRefinement(
        success=False,
        main_results=None,
        tokens=0,
        latency_ms=_elapsed_ms(started_at),
        retry_count=0,
        error=str(error)[:800],
    )


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
