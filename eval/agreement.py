"""A1：计算原标注与独立复核在三个低分字段上的一致性。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.models import PaperRecord
from eval.metrics import (
    atomic_fact_precision_recall_f1,
    fuzzy_match,
    load_ground_truth,
)


FIELDS = ("method_name", "experimental_conditions", "main_results")


def load_rechecks(directory: Path | str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """读取只含三个字段的独立复核文件。"""

    records: dict[str, dict[str, Any]] = {}
    invalid: list[str] = []
    for path in sorted(Path(directory).glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            filename = str(payload["filename"]).strip()
            review = payload["review"]
            if payload.get("needs_review", True) or not filename or not isinstance(review, dict):
                invalid.append(path.name)
                continue
            if not isinstance(review.get("experimental_conditions"), list) or not isinstance(review.get("main_results"), list):
                invalid.append(path.name)
                continue
            records[filename.casefold()] = review
        except (OSError, ValueError, KeyError, TypeError):
            invalid.append(path.name)
    return records, invalid


def compute_agreement(
    ground_truth_dir: Path | str,
    recheck_dir: Path | str,
    *,
    method_threshold: float = 0.9,
) -> dict[str, Any]:
    """复用项目当前匹配规则，计算标注者之间的字段一致性。"""

    original = load_ground_truth(ground_truth_dir)
    if original.pending_files or original.invalid_files:
        raise ValueError("原标注目录存在待确认或无效文件")
    rechecks, invalid = load_rechecks(recheck_dir)
    common = sorted(set(original.records) & set(rechecks))
    if not common:
        raise ValueError("两份标注没有共同论文")

    fields: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for filename in common:
        original_record: PaperRecord = original.records[filename]
        review = rechecks[filename]
        method_score = float(
            fuzzy_match(original_record.method_name, review.get("method_name"), method_threshold)
        )
        condition_p, condition_r, condition_f1 = atomic_fact_precision_recall_f1(
            original_record.experimental_conditions, review["experimental_conditions"]
        )
        result_p, result_r, result_f1 = atomic_fact_precision_recall_f1(
            original_record.main_results, review["main_results"]
        )
        rows.append(
            {
                "filename": filename,
                "method_name_score": method_score,
                "experimental_conditions_precision": condition_p,
                "experimental_conditions_recall": condition_r,
                "experimental_conditions_f1": condition_f1,
                "main_results_precision": result_p,
                "main_results_recall": result_r,
                "main_results_f1": result_f1,
            }
        )

    fields["method_name"] = {"kind": "fuzzy_accuracy", "score": _mean(rows, "method_name_score")}
    for field in ("experimental_conditions", "main_results"):
        fields[field] = {
            "kind": "atomic_fact_set",
            "precision": _mean(rows, f"{field}_precision"),
            "recall": _mean(rows, f"{field}_recall"),
            "f1": _mean(rows, f"{field}_f1"),
            "score": _mean(rows, f"{field}_f1"),
        }
    return {
        "sample_count": len(common),
        "files": common,
        "fields": fields,
        "rows": rows,
        "invalid_rechecks": invalid,
        "unmatched_rechecks": sorted(set(rechecks) - set(original.records)),
    }


def write_agreement(report: dict[str, Any], output_path: Path) -> None:
    """同时写入机器可读 JSON 与简洁 Markdown 报告。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# A1 标注一致性报告",
        "",
        "> 这是原标注与独立复核之间的规则一致性，不等同于严格的人类自一致性。",
        f"> 复核论文：{report['sample_count']} 篇。",
        "",
        "| 字段 | 一致性规则 | Precision | Recall | 分数 |",
        "|---|---|---:|---:|---:|",
    ]
    for field in FIELDS:
        metric = report["fields"][field]
        if field == "method_name":
            lines.append(f"| 方法名称 | 模糊匹配 Accuracy | — | — | {metric['score']:.2%} |")
        else:
            lines.append(
                f"| {field} | 原子事实集合 F1 | {metric['precision']:.2%} | "
                f"{metric['recall']:.2%} | {metric['f1']:.2%} |"
            )
    output_path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="计算 A1 原标注与复核标注的一致性")
    parser.add_argument("--ground-truth", type=Path, default=Path("eval/ground_truth/evaluation"))
    parser.add_argument("--recheck-dir", type=Path, default=Path("eval/ground_truth_recheck"))
    parser.add_argument("--output", type=Path, default=Path("eval/output/diagnosis/agreement.json"))
    parser.add_argument("--expected-sample-count", type=int, default=8)
    args = parser.parse_args()
    report = compute_agreement(args.ground_truth, args.recheck_dir)
    if report["sample_count"] != args.expected_sample_count:
        raise ValueError(
            f"独立复核应有 {args.expected_sample_count} 篇共同论文，实际为 {report['sample_count']} 篇"
        )
    write_agreement(report, args.output)
    print(f"A1 报告已保存：{args.output.resolve()}")


if __name__ == "__main__":
    main()
