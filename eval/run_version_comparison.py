"""比较两个 Prompt 版本在同一份已确认盲测集上的表现。"""

from __future__ import annotations

import argparse
from pathlib import Path

from eval.metrics import load_ground_truth, load_predictions
from eval.reporting import build_comparison, write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="生成两个 Prompt 版本的公平对比报告")
    parser.add_argument(
        "--ground-truth", type=Path, default=Path("eval/ground_truth/evaluation")
    )
    parser.add_argument(
        "--v1", type=Path, default=Path("eval/predictions/no_retry.json")
    )
    parser.add_argument(
        "--v2",
        type=Path,
        default=Path("eval/predictions/v2-evaluation/predictions.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("eval/output/v1-v2-comparison")
    )
    parser.add_argument("--baseline-label", default="V1")
    parser.add_argument("--comparison-label", default="V2")
    args = parser.parse_args()

    labels = load_ground_truth(args.ground_truth)
    if labels.invalid_files or labels.pending_files:
        raise ValueError("对比前必须确保评测标签全部确认且有效")
    v1 = load_predictions(args.v1)
    v2 = load_predictions(args.v2)
    report = build_comparison(
        labels,
        v1,
        v2,
        baseline_label=args.baseline_label,
        comparison_label=args.comparison_label,
    )
    paths = write_report(report, args.output_dir)
    print(f"{args.baseline_label}：{report['baseline']['overall_auto_score']:.2%}")
    print(f"{args.comparison_label}：{report['with_retries']['overall_auto_score']:.2%}")
    print(f"绝对提升：{report['overall_delta'] * 100:+.2f} 个百分点")
    for kind, path in paths.items():
        print(f"{kind}: {path.resolve()}")


if __name__ == "__main__":
    main()
