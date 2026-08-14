"""仅按冻结协议复算 final-holdout-v1 的方法名称度量 v2。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval.metrics import (
    evaluate_records,
    fuzzy_match,
    load_ground_truth,
    load_predictions,
    method_name_metric_v2_match,
    method_name_metric_v2_match_detail,
)


def build_report(labels_dir: Path, baseline_path: Path, robust_path: Path) -> dict[str, Any]:
    labels = load_ground_truth(labels_dir)
    if labels.pending_files or labels.invalid_files:
        raise ValueError("最终留出集标签必须全部确认且有效")
    baseline_predictions = load_predictions(baseline_path)
    robust_predictions = load_predictions(robust_path)
    v1_baseline = evaluate_records(labels.records, baseline_predictions)
    v1_robust = evaluate_records(labels.records, robust_predictions)
    v2_baseline = evaluate_records(
        labels.records, baseline_predictions, method_name_matcher=method_name_metric_v2_match
    )
    v2_robust = evaluate_records(
        labels.records, robust_predictions, method_name_matcher=method_name_metric_v2_match
    )

    remaining = []
    changed = []
    for filename, truth in sorted(labels.records.items()):
        actual = robust_predictions.get(filename, {}).get("method_name")
        before = fuzzy_match(truth.method_name, actual, threshold=0.9)
        after, reason = method_name_metric_v2_match_detail(truth.method_name, actual)
        row = {
            "filename": filename,
            "ground_truth": truth.method_name,
            "prediction": actual,
            "v1": before,
            "v2": after,
            "reason": reason,
        }
        if before != after:
            changed.append(row)
        if not after:
            remaining.append(row)
    return {
        "scope": {
            "api_called": False,
            "frozen_holdout": "final-holdout-v1",
            "information_leakage_note": "本次规则修正在看过留出集失败样例后设计，存在轻微信息泄漏；严格验证必须在新数据集上进行。",
            "protocol": "仅允许空值对齐、括号缩写与首字母缩写；0.90 阈值保持不变。",
        },
        "v1_baseline": v1_baseline,
        "v2_baseline": v2_baseline,
        "v1_robust": v1_robust,
        "v2_robust": v2_robust,
        "changed_cases": changed,
        "remaining_incorrect_cases": remaining,
    }


def render_markdown(report: dict[str, Any]) -> str:
    rows = [
        ("方法名称（无修正重试）", report["v1_baseline"]["fields"]["method_name"]["score"], report["v2_baseline"]["fields"]["method_name"]["score"]),
        ("方法名称（三级容错）", report["v1_robust"]["fields"]["method_name"]["score"], report["v2_robust"]["fields"]["method_name"]["score"]),
        ("8 字段宏平均（无修正重试）", report["v1_baseline"]["overall_auto_score"], report["v2_baseline"]["overall_auto_score"]),
        ("8 字段宏平均（三级容错）", report["v1_robust"]["overall_auto_score"], report["v2_robust"]["overall_auto_score"]),
    ]
    lines = [
        "# final-holdout-v1：方法名称度量 v2",
        "",
        "> 本报告只复算评分，不调用 API、不修改 Prompt、阈值或抽取结果。v1 和 v2 永久并列保留。",
        "",
        "## 严格协议",
        "",
        "- 保持原 0.90 fuzzy 阈值不变。",
        "- 只新增：双方为空时匹配；括号内纯缩写与另一侧匹配；纯缩写与另一侧首字母缩写匹配。",
        "- 不加入同义词表、语义相似度、阈值调整或其他宽松规则。",
        "",
        "## 得分对照",
        "",
        "| 字段 | v1 规则 | v2 规则 | 差值 |",
        "|---|---:|---:|---:|",
    ]
    for label, v1, v2 in rows:
        lines.append(f"| {label} | {v1:.2%} | {v2:.2%} | {v2-v1:+.2%} |")
    lines.extend(
        [
            "",
            "## 发生变化的三级容错样例",
            "",
            "| 论文 | 命中规则 | 人工标注 | 模型输出 |",
            "|---|---|---|---|",
        ]
    )
    for row in report["changed_cases"]:
        lines.append(
            f"| {row['filename']} | {row['reason']} | {row['ground_truth']} | {row['prediction']} |"
        )
    if not report["changed_cases"]:
        lines.append("| 无 | - | - | - |")
    lines.extend(
        [
            "",
            f"## v2 仍判错：{len(report['remaining_incorrect_cases'])} 条",
            "",
            "| 论文 | 人工标注 | 模型输出 | 情况 |",
            "|---|---|---|---|",
        ]
    )
    for row in report["remaining_incorrect_cases"]:
        lines.append(
            f"| {row['filename']} | {row['ground_truth']} | {row['prediction']} | {row['reason']} |"
        )
    lines.extend(["", f"> {report['scope']['information_leakage_note']}"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="复算 final-holdout-v1 方法名称度量 v2")
    parser.add_argument("--ground-truth", type=Path, default=Path("eval/ground_truth_final_holdout"))
    parser.add_argument("--baseline", type=Path, default=Path("eval/predictions/final-holdout-v1/no_retry.json"))
    parser.add_argument("--robust", type=Path, default=Path("eval/predictions/final-holdout-v1/with_retries.json"))
    parser.add_argument("--output", type=Path, default=Path("eval/output/final-holdout-v1/method-name-metric-v2.md"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"协议要求只运行一次，拒绝覆盖既有报告：{args.output}")
    report = build_report(args.ground_truth, args.baseline, args.robust)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(report), encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"方法名称 v2 报告：{args.output}")


if __name__ == "__main__":
    main()
