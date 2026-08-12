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
    experimental_conditions: list[str] = Field(
        default_factory=list,
        description="实验条件，如调制格式、波特率、传输距离、频率、功率和采样率",
    )
    main_results: list[str] = Field(default_factory=list)
    limitations: str | None = None
    summary: str = Field(min_length=1, max_length=400)

    @field_validator("authors", "experimental_conditions", "main_results")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        """清理列表中的空白项，同时保留原来的先后顺序。"""

        normalized: list[str] = []
        for value in values:
            cleaned = value.strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @field_validator("experimental_conditions")
    @classmethod
    def conditions_must_be_explicit(cls, values: list[str]) -> list[str]:
        """实验条件数组只接受原文明确给出的条件，不接受缺失说明或推断。"""

        forbidden_markers = (
            "未明确",
            "未给出",
            "推断",
            "不列入",
            "not specified",
            "not explicitly",
            "inferred",
        )
        invalid = [
            value
            for value in values
            if any(marker in value.casefold() for marker in forbidden_markers)
        ]
        if invalid:
            raise ValueError(
                "experimental_conditions 只能包含原文明确给出的实验条件；"
                f"删除缺失说明或推断项：{invalid}"
            )
        return values

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

    @field_validator("limitations")
    @classmethod
    def limitations_must_not_be_inferred(cls, value: str | None) -> str | None:
        """拒绝模型用“可能”等措辞自行推测论文局限。"""

        if value is None:
            return None
        inference_markers = (
            "未明确提及",
            "未明确陈述",
            "没有明确提及",
            "未给出局限",
            "可能受限",
            "可能存在",
            "可能是",
            "推测",
            "或许",
            "maybe",
            "may be limited",
            "might be limited",
            "not explicitly stated",
            "not mentioned",
        )
        lowered = value.casefold()
        if any(marker.casefold() in lowered for marker in inference_markers):
            raise ValueError("limitations 只能来自作者明确陈述，不能使用推测性措辞")
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

    PARSE = "parse"
    INPUT = "input"
    API_ERROR = "api_error"
    JSON_PARSE = "json_parse"
    SCHEMA_VALIDATE = "schema_validate"
    PIPELINE = "pipeline"
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


class BatchProgressStatus(str, Enum):
    """进度回调向控制台、API 或界面报告的单文件最终状态。"""

    SUCCESS = "success"
    FAILED = "failed"


class BatchFileResult(BaseModel):
    """M4 对一份输入文件的稳定处理结果。"""

    path: Path
    filename: str = Field(min_length=1)
    success: bool
    record: PaperRecord | None = None
    failure: ExtractionFailure | None = None
    retry_count: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    attempts: list[ExtractionAttempt] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_matching_batch_payload(self) -> "BatchFileResult":
        """成功项必须带记录，失败项必须带诊断，避免下游猜测数据状态。"""

        if self.success and (self.record is None or self.failure is not None):
            raise ValueError("成功文件必须包含 record，且不能包含 failure")
        if not self.success and (self.failure is None or self.record is not None):
            raise ValueError("失败文件必须包含 failure，且不能包含 record")
        return self


class BatchResult(BaseModel):
    """一批文件的汇总结果，后续由 M5 持久化。"""

    total_files: int = Field(ge=0)
    success_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    total_tokens: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    files: list[BatchFileResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def counts_must_match_files(self) -> "BatchResult":
        """防止汇总数字与文件明细不一致。"""

        successes = sum(item.success for item in self.files)
        failures = len(self.files) - successes
        if self.total_files != len(self.files):
            raise ValueError("total_files 必须等于文件明细数量")
        if self.success_count != successes or self.fail_count != failures:
            raise ValueError("成功/失败汇总必须与文件明细一致")
        if self.total_tokens != sum(item.total_tokens for item in self.files):
            raise ValueError("total_tokens 必须等于所有文件 token 之和")
        return self
