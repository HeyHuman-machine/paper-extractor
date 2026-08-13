"""定位 V1/V2 在每篇论文、每个字段上的失分，辅助开发集调优。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from eval.metrics import AUTO_FIELDS, FIELD_LABELS, evaluate_records, load_ground_truth, load_predictions


def build_diagnosis(
    ground_truth_dir: Path | str,
    v1_path: Path | str,
    v2_path: Path | str,
    *,
    baseline_label: str = "V1",
    comparison_label: str = "V2",
) -> dict[str, Any]:
    """为同一批已确认标注生成字段和论文粒度的 V1/V2 分数。"""

    labels = load_ground_truth(ground_truth_dir)
    if labels.invalid_files or labels.pending_files:
        raise ValueError("诊断前必须确保标注全部确认且有效")
    v1 = load_predictions(v1_path)
    v2 = load_predictions(v2_path)
    papers: list[dict[str, Any]] = []
    for filename, truth in labels.records.items():
        before = evaluate_records({filename: truth}, {filename: v1[filename]})
        after = evaluate_records({filename: truth}, {filename: v2[filename]})
        papers.append(
            {
                "filename": filename,
                "fields": {
                    field: {
                        "v1": before["fields"][field]["score"],
                        "v2": after["fields"][field]["score"],
                    }
                    for field in AUTO_FIELDS
                },
            }
        )
    return {
        "paper_count": len(papers),
        "baseline_label": baseline_label,
        "comparison_label": comparison_label,
        "papers": papers,
    }


def _markdown(diagnosis: dict[str, Any]) -> str:
    lines = [
        f"# {diagnosis['baseline_label']}-{diagnosis['comparison_label']} 字段误差诊断",
        "",
        f"> 已比较论文：{diagnosis['paper_count']} 篇",
        "> 分数为单篇字段得分；0 表示该字段完全未匹配，1 表示完全匹配。",
        "",
    ]
    for field in AUTO_FIELDS:
        low_rows = sorted(
            (
                (
                    paper["fields"][field]["v2"],
                    paper["fields"][field]["v1"],
                    paper["filename"],
                )
                for paper in diagnosis["papers"]
                if (
                    paper["fields"][field]["v1"] < 1
                    or paper["fields"][field]["v2"] < 1
                )
            ),
        )
        lines.extend(
            [
                f"## {FIELD_LABELS[field]}",
                "",
                f"| 论文 | {diagnosis['baseline_label']} | {diagnosis['comparison_label']} | {diagnosis['comparison_label']} 状态 |",
                "|---|---:|---:|---|",
            ]
        )
        if not low_rows:
            lines.append("| 全部论文 | 100.00% | 100.00% | 无失分 |")
        else:
            for v2_score, v1_score, filename in low_rows:
                status = "改善" if v2_score > v1_score else "下降" if v2_score < v1_score else "未改善"
                lines.append(
                    f"| {filename} | {v1_score:.2%} | {v2_score:.2%} | {status} |"
                )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成两个 Prompt 版本的字段误差诊断")
    parser.add_argument(
        "--ground-truth", type=Path, default=Path("eval/ground_truth/evaluation")
    )
    parser.add_argument("--v1", type=Path, default=Path("eval/predictions/no_retry.json"))
    parser.add_argument(
        "--v2", type=Path, default=Path("eval/predictions/v2-evaluation/predictions.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("eval/output/v1-v2-comparison/field_diagnosis.md")
    )
    parser.add_argument("--baseline-label", default="V1")
    parser.add_argument("--comparison-label", default="V2")
    args = parser.parse_args()
    diagnosis = build_diagnosis(
        args.ground_truth,
        args.v1,
        args.v2,
        baseline_label=args.baseline_label,
        comparison_label=args.comparison_label,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_markdown(diagnosis), encoding="utf-8")
    print(f"字段诊断已保存：{args.output.resolve()}")


if __name__ == "__main__":
    main()
