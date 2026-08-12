"""项目中共享的数据模型。

同一份 ``PaperRecord`` 会在后续模块中用于 LLM 输出校验、FastAPI 响应模型
和评测脚本，避免三个地方各写一套字段定义。
"""

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DocumentType(str, Enum):
    """论文文档类型的固定取值。"""

    CONFERENCE_PAPER = "conference_paper"
    JOURNAL_ARTICLE = "journal_article"
    PREPRINT = "preprint"
    THESIS = "thesis"
    SURVEY = "survey"
    OTHER = "other"


class PaperRecord(BaseModel):
    """一篇论文需要抽取的11个结构化字段。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, description="论文标题")
    authors: list[str] = Field(min_length=1, description="作者列表")
    year: int | None = Field(default=None, ge=1950, le=2030)
    venue: str | None = None
    doc_type: DocumentType
    problem: str = Field(min_length=1, max_length=200)
    method_name: str | None = None
    datasets: list[str] = Field(default_factory=list)
    main_results: list[str] = Field(default_factory=list)
    limitations: str | None = None
    summary: str = Field(min_length=1, max_length=400)

    @field_validator("authors", "datasets", "main_results")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        """清理列表中的空白项，同时保留原来的先后顺序。"""

        normalized: list[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @field_validator("authors")
    @classmethod
    def require_non_empty_author(cls, authors: list[str]) -> list[str]:
        """防止 ``[""]`` 这种表面有一项、实际没有作者的结果通过校验。"""

        if not authors:
            raise ValueError("authors 至少需要一位非空作者")
        return authors

    @field_validator("venue", "method_name", "limitations", mode="before")
    @classmethod
    def empty_optional_string_to_none(cls, value: Any) -> Any:
        """把可选字段中的空字符串统一转换为 ``None``。"""

        if isinstance(value, str) and not value.strip():
            return None
        return value


class ParsedDoc(BaseModel):
    """文档解析器返回的统一结果。"""

    path: Path
    file_name: str
    file_type: str
    page_count: int = Field(ge=1)
    text: str = Field(min_length=1)
    pages: list[str] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """一次成功的大模型调用结果及其可观测指标。"""

    content: str = Field(min_length=1, description="模型返回的正文")
    model: str = Field(min_length=1, description="服务端实际使用的模型")
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(ge=0, description="包含重试等待在内的总耗时")
    retry_count: int = Field(default=0, ge=0)


class ExtractionStage(str, Enum):
    """抽取流程中可诊断的处理阶段。"""

    INPUT = "input"
    API_ERROR = "api_error"
    JSON_PARSE = "json_parse"
    SCHEMA_VALIDATE = "schema_validate"
    SUCCESS = "success"


class ExtractionAttempt(BaseModel):
    """一次模型调用的原始输出、指标和校验结果。"""

    attempt_number: int = Field(ge=1)
    stage: ExtractionStage
    raw_output: str | None = None
    error_type: str | None = None
    error_msg: str | None = None
    tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    transport_retry_count: int = Field(default=0, ge=0)


class ExtractionFailure(BaseModel):
    """重试耗尽或 API 失败后的最终诊断信息。"""

    stage: ExtractionStage
    error_type: str
    error_msg: str
    raw_llm_output: str | None = None


class ExtractionResult(BaseModel):
    """M3 的统一返回值：失败也作为数据返回，不中断后续批处理。"""

    success: bool
    record: PaperRecord | None = None
    failure: ExtractionFailure | None = None
    retry_count: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_latency_ms: int = Field(default=0, ge=0)
    attempts: list[ExtractionAttempt] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_matching_payload(self) -> "ExtractionResult":
        """成功时必须有论文记录，失败时必须有失败诊断。"""

        if self.success and (self.record is None or self.failure is not None):
            raise ValueError("成功结果必须包含 record，且不能包含 failure")
        if not self.success and (self.failure is None or self.record is not None):
            raise ValueError("失败结果必须包含 failure，且不能包含 record")
        return self
