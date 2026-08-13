"""命令行入口：运行阶段 A 的 A2-A6 诊断导出。"""

from __future__ import annotations

import argparse
from pathlib import Path

from eval.agreement import compute_agreement, write_agreement
from eval.diagnostics import build_diagnostics, write_diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 A2-A6 诊断交付物")
    parser.add_argument("--ground-truth", type=Path, default=Path("eval/ground_truth/evaluation"))
    parser.add_argument("--predictions", type=Path, default=Path("eval/predictions/v2-evaluation/predictions.json"))
    parser.add_argument("--recheck-dir", type=Path, default=Path("eval/ground_truth_recheck"))
    parser.add_argument("--output-dir", type=Path, default=Path("eval/output/diagnosis"))
    args = parser.parse_args()

    agreement = compute_agreement(args.ground_truth, args.recheck_dir)
    diagnosis = build_diagnostics(args.ground_truth, args.predictions)
    paths = write_diagnostics(
        diagnosis,
        args.output_dir,
        metrics_source=Path("eval/metrics.py"),
        agreement=agreement,
    )
    agreement_path = args.output_dir / "agreement.json"
    write_agreement(agreement, agreement_path)
    print(f"诊断完成：{args.output_dir.resolve()}")
    for name, path in paths.items():
        print(f"{name}: {path.resolve()}")
    print(f"agreement: {agreement_path.resolve()}")


if __name__ == "__main__":
    main()
