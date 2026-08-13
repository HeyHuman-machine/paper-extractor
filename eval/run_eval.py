"""读取人工答案与两轮预测，生成 M9 真实评测报告。"""

from __future__ import annotations

import argparse
from pathlib import Path

from eval.metrics import load_ground_truth, load_predictions
from eval.reporting import build_comparison, write_report


def run_evaluation(
    ground_truth_dir: Path | str,
    baseline_path: Path | str,
    robust_path: Path | str,
    output_dir: Path | str,
    *,
    minimum_labels: int = 30,
    allow_partial: bool = False,
) -> tuple[dict, dict[str, Path]]:
    """运行评测；正式报告默认要求 30 篇独立盲测标注。"""

    labels = load_ground_truth(ground_truth_dir)
    if labels.invalid_files:
        raise ValueError(f"存在无效标注文件：{', '.join(labels.invalid_files)}")
    if len(labels.records) < minimum_labels and not allow_partial:
        raise ValueError(
            f"正式评测至少需要 {minimum_labels} 篇已确认标注，当前只有 "
            f"{len(labels.records)} 篇，另有 {len(labels.pending_files)} 篇待确认"
        )
    if not labels.records:
        raise ValueError("没有已确认标注；请把 needs_review 改为 false 后再运行")

    baseline = load_predictions(baseline_path)
    robust = load_predictions(robust_path)
    report = build_comparison(labels, baseline, robust)
    report["is_partial"] = len(labels.records) < minimum_labels
    paths = write_report(report, output_dir)
    return report, paths


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 M9 两轮准确率报告")
    parser.add_argument("--ground-truth", type=Path, default=Path("eval/ground_truth/evaluation"))
    parser.add_argument("--baseline", type=Path, default=Path("eval/predictions/no_retry.json"))
    parser.add_argument("--robust", type=Path, default=Path("eval/predictions/with_retries.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("eval/output"))
    parser.add_argument("--allow-partial", action="store_true", help="允许少于 30 篇，仅用于调试")
    args = parser.parse_args()
    report, paths = run_evaluation(
        args.ground_truth,
        args.baseline,
        args.robust,
        args.output_dir,
        allow_partial=args.allow_partial,
    )
    marker = "（部分样本，仅供调试）" if report["is_partial"] else ""
    print(f"评测完成{marker}")
    print(f"无重试：{report['baseline']['overall_auto_score']:.2%}")
    print(f"三级容错：{report['with_retries']['overall_auto_score']:.2%}")
    print(f"绝对提升：{report['overall_delta'] * 100:+.2f} 个百分点")
    for kind, path in paths.items():
        print(f"{kind}: {path.resolve()}")


if __name__ == "__main__":
    main()
