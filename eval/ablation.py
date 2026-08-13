"""B0：三级容错消融实验。

三档运行共享文件、模型、Prompt、温度、并发和 HTTP 网络重试；只改变 M3
内容层的 JSON 清洗、Pydantic 校验与内容修正重试。无容错组并不在运行路径中
做 Pydantic 校验，但报告会对原始字典做一次事后只读校验，以统计其本可通过
schema 的比例，不把它用作接收、回退或重试条件。
"""

from __future__ import annotations

import json
import statistics
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from app.config import Settings
from app.extractor import Extractor
from app.llm import LLMClient, LLMError
from app.models import ExtractionStage, PaperRecord
from app.parser import DocumentParserError, parse_document, smart_truncate
from app.prompts import build_extraction_messages
from eval.metrics import AUTO_FIELDS, FIELD_LABELS, evaluate_records, load_ground_truth


AblationMode = Literal["no_fault_tolerance", "parse_and_validate", "full_three_layer"]
ALL_FIELDS = tuple(PaperRecord.model_fields)


@dataclass(frozen=True, slots=True)
class ModeSpec:
    key: AblationMode
    label: str
    tolerant_json_parse: bool
    schema_validation_in_flow: bool
    max_repair_retries: int


MODE_SPECS: tuple[ModeSpec, ...] = (
    ModeSpec(
        key="no_fault_tolerance",
        label="① 无容错",
        tolerant_json_parse=False,
        schema_validation_in_flow=False,
        max_repair_retries=0,
    ),
    ModeSpec(
        key="parse_and_validate",
        label="② 仅解析容错 + Pydantic 校验",
        tolerant_json_parse=True,
        schema_validation_in_flow=True,
        max_repair_retries=0,
    ),
    ModeSpec(
        key="full_three_layer",
        label="③ 完整三级容错",
        tolerant_json_parse=True,
        schema_validation_in_flow=True,
        max_repair_retries=2,
    ),
)


def run_ablation(
    files: list[Path], settings: Settings, *, concurrency: int | None = None
) -> dict[str, Any]:
    """对同一份文件按三个配置依次运行真实抽取。"""

    worker_count = concurrency if concurrency is not None else settings.batch_concurrency
    if worker_count < 1:
        raise ValueError("concurrency 必须大于等于 1")
    runs = []
    for spec in MODE_SPECS:
        started_at = time.perf_counter()
        with LLMClient(settings=settings) as client:
            records = _run_mode(files, settings, client, spec, worker_count)
        runs.append(
            {
                "mode": spec.key,
                "label": spec.label,
                "flow": {
                    "tolerant_json_parse": spec.tolerant_json_parse,
                    "schema_validation_in_flow": spec.schema_validation_in_flow,
                    "max_repair_retries": spec.max_repair_retries,
                    "transport_retries": settings.llm_max_retries,
                },
                "summary": _summarize(records, elapsed_ms=_elapsed_ms(started_at)),
                "papers": records,
            }
        )
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "experiment": "B0_three_layer_fault_tolerance_ablation",
        "shared_config": {
            "model": settings.llm_model,
            "temperature": 0.0,
            "thinking_enabled": settings.llm_thinking_enabled,
            "json_mode": settings.llm_json_mode,
            "extract_max_chars": settings.extract_max_chars,
            "batch_concurrency": worker_count,
            "transport_retries": settings.llm_max_retries,
            "input_files": [path.name for path in files],
        },
        "runs": runs,
    }


def score_ablation(
    payload: dict[str, Any], ground_truth_dir: Path | str
) -> dict[str, Any]:
    """以冻结标注对三档输出评分；schema 未通过的输出按缺失预测计零分。"""

    labels = load_ground_truth(ground_truth_dir)
    if labels.pending_files or labels.invalid_files:
        raise ValueError("B0 评分需要完整、已确认且有效的冻结标注")
    for run in payload["runs"]:
        predictions = {
            paper["filename"].casefold(): paper["normalized_record"]
            for paper in run["papers"]
            if paper["posthoc_schema_valid"] and paper["normalized_record"] is not None
        }
        run["field_metrics"] = evaluate_records(labels.records, predictions)
    return payload


def write_ablation_report(payload: dict[str, Any], output_dir: Path | str) -> dict[str, Path]:
    """写出完整原始明细、摘要 JSON 与可读 Markdown。"""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / "ablation_raw.json"
    summary_path = directory / "ablation_summary.json"
    markdown_path = directory / "ablation_report.md"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "generated_at": payload["generated_at"],
        "experiment": payload["experiment"],
        "shared_config": payload["shared_config"],
        "runs": [
            {
                "mode": run["mode"],
                "label": run["label"],
                "flow": run["flow"],
                "summary": run["summary"],
                "field_metrics": run["field_metrics"],
            }
            for run in payload["runs"]
        ],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(summary), encoding="utf-8")
    return {"raw": raw_path, "summary": summary_path, "markdown": markdown_path}


def _run_mode(
    files: list[Path],
    settings: Settings,
    client: LLMClient,
    spec: ModeSpec,
    concurrency: int,
) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any] | None] = [None] * len(files)
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="paper-ablation") as executor:
        futures: dict[Future[dict[str, Any]], int] = {
            executor.submit(_run_one, path, settings, client, spec): index
            for index, path in enumerate(files)
        }
        completed = 0
        for future in as_completed(futures):
            index = futures[future]
            try:
                item = future.result()
            except Exception as exc:  # 最外层保险：单篇异常不停止其余 API 运行。
                item = _unhandled_failure(files[index], exc)
            ordered[index] = item
            completed += 1
            status = "SUCCESS" if item["flow_success"] else "FAILED"
            print(f"[{spec.key} {completed}/{len(files)}] {status:7} {item['filename']}", flush=True)
    return [item for item in ordered if item is not None]


def _run_one(path: Path, settings: Settings, client: LLMClient, spec: ModeSpec) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        document = parse_document(path)
    except DocumentParserError as exc:
        return _failure(path, ExtractionStage.PARSE.value, exc, started_at)
    except Exception as exc:
        return _failure(path, ExtractionStage.PIPELINE.value, exc, started_at)

    if spec.key == "no_fault_tolerance":
        item = _strict_extract(path, document.text, settings, client, started_at)
    else:
        extractor = Extractor(
            settings,
            client,
            max_repair_retries=spec.max_repair_retries,
        )
        extraction = extractor.extract(document.text)
        item = {
            "filename": path.name,
            "flow_success": extraction.success,
            "failure_stage": extraction.failure.stage.value if extraction.failure else None,
            "failure_type": extraction.failure.error_type if extraction.failure else None,
            "failure_message": extraction.failure.error_msg if extraction.failure else None,
            "raw_record": extraction.record.model_dump(mode="json") if extraction.record else None,
            "attempts": [_attempt_summary(attempt) for attempt in extraction.attempts],
            "duration_ms": _elapsed_ms(started_at),
        }
    _add_posthoc_measurements(item)
    return item


def _strict_extract(
    path: Path, text: str, settings: Settings, client: LLMClient, started_at: float
) -> dict[str, Any]:
    """无容错组：精确 JSON，不扫描代码块，不做 Pydantic，不做内容修正。"""

    try:
        messages = build_extraction_messages(smart_truncate(text.strip(), settings.extract_max_chars))
        response = client.chat(messages, max_tokens=1200, temperature=0.0)
    except (LLMError, ValueError) as exc:
        return _failure(path, ExtractionStage.API_ERROR.value, exc, started_at)
    try:
        raw = json.loads(response.content)
        if not isinstance(raw, dict):
            raise ValueError("严格 JSON 顶层不是对象")
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            **_failure(path, ExtractionStage.JSON_PARSE.value, exc, started_at),
            "attempts": [_strict_attempt(response, ExtractionStage.JSON_PARSE.value, exc)],
        }
    return {
        "filename": path.name,
        "flow_success": True,
        "failure_stage": None,
        "failure_type": None,
        "failure_message": None,
        "raw_record": raw,
        "attempts": [_strict_attempt(response, ExtractionStage.SUCCESS.value, None)],
        "duration_ms": _elapsed_ms(started_at),
    }


def _add_posthoc_measurements(item: dict[str, Any]) -> None:
    raw = item.get("raw_record")
    item["posthoc_schema_valid"] = False
    item["normalized_record"] = None
    if isinstance(raw, dict):
        try:
            item["normalized_record"] = PaperRecord.model_validate(raw).model_dump(mode="json")
            item["posthoc_schema_valid"] = True
        except ValidationError:
            pass
    record = raw if isinstance(raw, dict) else {}
    item["non_empty_field_count"] = sum(_is_non_empty(record.get(field)) for field in ALL_FIELDS)
    item["field_completeness"] = item["non_empty_field_count"] / len(ALL_FIELDS)


def _failure(path: Path, stage: str, error: Exception, started_at: float) -> dict[str, Any]:
    return {
        "filename": path.name,
        "flow_success": False,
        "failure_stage": stage,
        "failure_type": type(error).__name__,
        "failure_message": (str(error).strip() or type(error).__name__)[:500],
        "raw_record": None,
        "attempts": [],
        "duration_ms": _elapsed_ms(started_at),
    }


def _unhandled_failure(path: Path, error: Exception) -> dict[str, Any]:
    item = _failure(path, ExtractionStage.PIPELINE.value, error, time.perf_counter())
    _add_posthoc_measurements(item)
    return item


def _strict_attempt(response: Any, stage: str, error: Exception | None) -> dict[str, Any]:
    return {
        "stage": stage,
        "tokens": response.total_tokens,
        "latency_ms": response.latency_ms,
        "transport_retry_count": response.retry_count,
        "error_type": type(error).__name__ if error else None,
    }


def _attempt_summary(attempt: Any) -> dict[str, Any]:
    return {
        "stage": attempt.stage.value,
        "tokens": attempt.tokens,
        "latency_ms": attempt.latency_ms,
        "transport_retry_count": attempt.transport_retry_count,
        "error_type": attempt.error_type,
    }


def _summarize(records: list[dict[str, Any]], *, elapsed_ms: int) -> dict[str, Any]:
    total = len(records)
    attempts = [attempt for record in records for attempt in record["attempts"]]
    model_calls = len(attempts)
    return {
        "total_files": total,
        "flow_success_count": sum(record["flow_success"] for record in records),
        "posthoc_schema_valid_count": sum(record["posthoc_schema_valid"] for record in records),
        "field_completeness": _mean([record["field_completeness"] for record in records]),
        "average_content_repair_retries": _mean([max(len(record["attempts"]) - 1, 0) for record in records]),
        "average_transport_retries_per_paper": _mean([sum(attempt["transport_retry_count"] for attempt in record["attempts"]) for record in records]),
        "average_model_calls_per_paper": model_calls / total if total else 0.0,
        "total_tokens": sum(attempt["tokens"] for attempt in attempts),
        "average_tokens_per_paper": _mean([sum(attempt["tokens"] for attempt in record["attempts"]) for record in records]),
        "average_duration_seconds_per_paper": _mean([record["duration_ms"] / 1000 for record in records]),
        "wall_clock_seconds": elapsed_ms / 1000,
        "failure_stages": _failure_stage_counts(records),
    }


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# B0：三级容错消融实验报告",
        "",
        "> 同一批 30 篇论文、同一模型、同一 Prompt、温度 0、并发和 HTTP 网络重试均保持一致；只改变 JSON 清洗、Pydantic 校验与内容修正重试。",
        "> 无容错组不在运行路径中做 Schema 校验；表中的“事后 Schema 合法”仅用于测量，不会触发接收或重试。",
        "",
        "## 工程稳定性与成本",
        "",
        "| 配置 | 流程成功 | 事后 Schema 合法 | 字段完整率 | 平均内容修正 | 平均网络重试 | 平均 Token/篇 | 平均耗时/篇 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run in summary["runs"]:
        value = run["summary"]
        lines.append(
            f"| {run['label']} | {value['flow_success_count']}/{value['total_files']} | "
            f"{value['posthoc_schema_valid_count']}/{value['total_files']} | "
            f"{value['field_completeness']:.2%} | {value['average_content_repair_retries']:.2f} | "
            f"{value['average_transport_retries_per_paper']:.2f} | {value['average_tokens_per_paper']:.0f} | "
            f"{value['average_duration_seconds_per_paper']:.2f}s |"
        )
    lines += ["", "## 字段质量（冻结人工标注）", "", "| 字段 | " + " | ".join(run["label"] for run in summary["runs"]) + " |", "|---|" + "|".join("---:" for _ in summary["runs"]) + "|"]
    for field in AUTO_FIELDS:
        values = " | ".join(f"{run['field_metrics']['fields'][field]['score']:.2%}" for run in summary["runs"])
        lines.append(f"| {FIELD_LABELS[field]} | {values} |")
    lines += ["", "## 8 字段宏平均", "", "| 配置 | 自动字段宏平均 |", "|---|---:|"]
    for run in summary["runs"]:
        lines.append(f"| {run['label']} | {run['field_metrics']['overall_auto_score']:.2%} |")
    lines += ["", "## 解读边界", "", "- B0 证明的是容错对**可用输出率、完整率、成本与当前字段得分**的影响，不等于 Prompt 或模型能力提升。", "- 所有评分均使用冻结的 30 篇标注；这批数据已暴露，不能据此继续调 Prompt 并宣称泛化。", "- 三档需要分别请求 API；即使温度为 0，服务端仍可能有轻微非确定性。因此字段分数是可复查的实测值；最强的因果证据是流程成功与 Schema 合法率的变化。", "- `ablation_raw.json` 保留逐篇状态、调用次数、Token、耗时与错误阶段，便于复核。", ""]
    return "\n".join(lines)


def _failure_stage_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        stage = record["failure_stage"]
        if stage:
            counts[stage] = counts.get(stage, 0) + 1
    return counts


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _mean(values: list[float | int]) -> float:
    return statistics.fmean(values) if values else 0.0


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
