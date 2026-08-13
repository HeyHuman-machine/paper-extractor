"""B2 试点评测：使用同一份结构化人工答案比较 V2 与结构化抽取输出。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from eval.metrics import _filename_key, load_predictions
from eval.structured_trial import (
    ConditionItem,
    ResultItem,
    StructuredFieldRecord,
    structured_precision_recall_f1,
)


_MEASUREMENT_PATTERN = re.compile(
    r"(?P<value>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*(?P<unit>tbaud|gbaud|mbaud|khz|mhz|ghz|thz|nm|km|dbm|db|%)?",
    re.IGNORECASE,
)


def load_structured_ground_truth(directory: Path | str) -> dict[str, StructuredFieldRecord]:
    """读取 B2 人工标注；任何待确认或无效文件都会阻止评分。"""

    records: dict[str, StructuredFieldRecord] = {}
    pending: list[str] = []
    invalid: list[str] = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            filename = str(payload["filename"])
            if payload.get("needs_review", True):
                pending.append(filename)
                continue
            records[_filename_key(filename)] = StructuredFieldRecord.model_validate(payload["record"])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            invalid.append(f"{path.name}: {exc}")
    if pending or invalid:
        raise ValueError(f"B2 标注尚未完成；待确认={pending}；无效={invalid}")
    return records


def legacy_prediction_to_structured(item: dict[str, Any]) -> StructuredFieldRecord:
    """以固定、可审计的解析规则把 V2 字符串列表投影为 B2 结构。"""

    conditions = [
        _legacy_condition(value)
        for value in item.get("experimental_conditions", [])
        if isinstance(value, str) and value.strip()
    ]
    results = [
        _legacy_result(value)
        for value in item.get("main_results", [])
        if isinstance(value, str) and value.strip()
    ]
    return StructuredFieldRecord(experimental_conditions=conditions, main_results=results)


def build_trial_report(
    labels_dir: Path | str,
    v2_predictions_path: Path | str,
    structured_predictions_path: Path | str,
) -> dict[str, Any]:
    """以相同 10 篇结构化答案计算 V2 基线与 B2 结果。"""

    truth = load_structured_ground_truth(labels_dir)
    v2_predictions = load_predictions(v2_predictions_path)
    structured_payload = json.loads(Path(structured_predictions_path).read_text(encoding="utf-8"))
    structured_predictions = {
        _filename_key(item["filename"]): StructuredFieldRecord.model_validate(item["record"])
        for item in structured_payload.get("results", [])
        if isinstance(item, dict) and item.get("filename") and isinstance(item.get("record"), dict)
    }
    if set(truth) != set(structured_predictions):
        missing = sorted(set(truth) - set(structured_predictions))
        extra = sorted(set(structured_predictions) - set(truth))
        raise ValueError(f"B2 预测与标注论文不一致；缺失={missing}；额外={extra}")

    baseline = {
        name: legacy_prediction_to_structured(v2_predictions.get(name, {}))
        for name in truth
    }
    return {
        "scope": {
            "ground_truth": str(labels_dir),
            "baseline": str(v2_predictions_path),
            "structured_trial": str(structured_predictions_path),
            "fairness": "两组均使用同一份 B2 结构化人工答案和同一套 partial-credit 规则评分。",
        },
        "paper_count": len(truth),
        "v2_baseline": _score_records(truth, baseline),
        "b2_structured": _score_records(truth, structured_predictions),
    }


def _score_records(
    truth: dict[str, StructuredFieldRecord], predictions: dict[str, StructuredFieldRecord]
) -> dict[str, Any]:
    fields: dict[str, dict[str, float]] = {}
    for field in ("experimental_conditions", "main_results"):
        scores = [
            structured_precision_recall_f1(
                getattr(expected, field),
                getattr(predictions[name], field),
            )
            for name, expected in truth.items()
        ]
        fields[field] = {
            "precision": sum(item.precision for item in scores) / len(scores),
            "recall": sum(item.recall for item in scores) / len(scores),
            "f1": sum(item.f1 for item in scores) / len(scores),
        }
    fields["mean_f1"] = {
        "score": (fields["experimental_conditions"]["f1"] + fields["main_results"]["f1"]) / 2
    }
    return fields


def render_report(report: dict[str, Any]) -> str:
    """渲染 B2 可读对照。"""

    baseline = report["v2_baseline"]
    candidate = report["b2_structured"]
    lines = [
        "# B2 结构化输出试点评测",
        "",
        f"- 试点论文：{report['paper_count']} 篇。",
        "- V2 旧输出与 B2 新输出均按同一份 B2 人工结构化答案评分。",
        "- V2 文本列表通过固定解析规则投影为结构化项；这不是重新调用 V2。",
        "",
        "| 字段 | V2 基线 F1 | B2 结构化 F1 | 变化 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for field, label in (("experimental_conditions", "实验条件"), ("main_results", "主要结果")):
        before = baseline[field]["f1"]
        after = candidate[field]["f1"]
        lines.append(f"| {label} | {before:.2%} | {after:.2%} | {after - before:+.2%} |")
    before = baseline["mean_f1"]["score"]
    after = candidate["mean_f1"]["score"]
    lines.extend([
        f"| 两字段平均 F1 | {before:.2%} | {after:.2%} | {after - before:+.2%} |",
        "",
        "> 结论只适用于固定 10 篇试点；只有改善清晰且人工答案可复核，才考虑推广至更多论文。",
        "",
    ])
    return "\n".join(lines)


def _legacy_condition(value: str) -> ConditionItem:
    name, raw_value = _split_once(value, ":")
    number, unit = _first_measurement(raw_value)
    return ConditionItem(name=name, value=number or raw_value.strip(), unit=unit)


def _legacy_result(value: str) -> ResultItem:
    primary, _, condition = value.partition("|")
    metric, raw_value = _split_once(primary, ":")
    number, unit = _first_measurement(raw_value)
    return ResultItem(
        metric=metric,
        value=number or raw_value.strip(),
        unit=unit,
        condition=_split_once(condition, ":")[1].strip() if condition else None,
    )


def _split_once(value: str, delimiter: str) -> tuple[str, str]:
    left, separator, right = value.partition(delimiter)
    return left.strip(), right.strip() if separator else ""


def _first_measurement(value: str) -> tuple[str | None, str | None]:
    match = _MEASUREMENT_PATTERN.search(value)
    if not match:
        return None, None
    return match.group("value"), match.group("unit")


def main() -> None:
    parser = argparse.ArgumentParser(description="B2 结构化输出试点评测")
    parser.add_argument("--labels", type=Path, default=Path("eval/ground_truth_structured_trial"))
    parser.add_argument("--v2", type=Path, default=Path("eval/predictions/v2-evaluation/predictions.json"))
    parser.add_argument("--b2", type=Path, default=Path("eval/predictions/b2-structured-pilot/predictions.json"))
    parser.add_argument("--output", type=Path, default=Path("eval/output/b2-structured-pilot/report.md"))
    args = parser.parse_args()
    report = build_trial_report(args.labels, args.v2, args.b2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(report), encoding="utf-8")
    print(f"B2 评测报告：{args.output.resolve()}")


if __name__ == "__main__":
    main()
