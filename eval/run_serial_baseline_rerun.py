"""以逐篇检查点串行模式复现 final-holdout-v1 的无内容修正对照组。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval.metrics import evaluate_records, load_ground_truth, load_predictions
from eval.run_checkpointed_predictions import run_checkpointed_predictions


def build_report(
    ground_truth_dir: Path | str,
    original_baseline_path: Path | str,
    serial_baseline_path: Path | str,
    robust_path: Path | str,
) -> dict[str, Any]:
    """比较原并发基线、串行基线和已冻结三级容错输出。"""

    labels = load_ground_truth(ground_truth_dir)
    if labels.pending_files or labels.invalid_files:
        raise ValueError("最终留出集标签必须全部确认且有效")
    original = load_predictions(original_baseline_path)
    serial = load_predictions(serial_baseline_path)
    robust = load_predictions(robust_path)
    original_payload = json.loads(Path(original_baseline_path).read_text(encoding="utf-8"))
    serial_payload = json.loads(Path(serial_baseline_path).read_text(encoding="utf-8"))
    serial_failure_by_file = {item["filename"].casefold(): item for item in serial_payload.get("failures", [])}

    status_changes = []
    definite_fault_tolerance = []
    run_variation_possible = []
    for filename in sorted(labels.records):
        original_success = filename in original
        serial_success = filename in serial
        robust_success = filename in robust
        if original_success != serial_success:
            status_changes.append(
                {
                    "filename": filename,
                    "original_parallel": "success" if original_success else "failed",
                    "serial_baseline": "success" if serial_success else "failed",
                }
            )
        if not serial_success and robust_success:
            definite_fault_tolerance.append(filename)
        if not original_success and serial_success:
            run_variation_possible.append(filename)

    return {
        "original_parallel_summary": original_payload["summary"],
        "serial_baseline_summary": serial_payload["summary"],
        "serial_baseline_failures": list(serial_failure_by_file.values()),
        "status_changes": status_changes,
        "original_parallel_metrics": evaluate_records(labels.records, original),
        "serial_baseline_metrics": evaluate_records(labels.records, serial),
        "robust_metrics": evaluate_records(labels.records, robust),
        "definite_fault_tolerance_files": definite_fault_tolerance,
        "run_variation_possible_files": run_variation_possible,
    }


def render_markdown(report: dict[str, Any]) -> str:
    serial = report["serial_baseline_metrics"]
    original = report["original_parallel_metrics"]
    robust = report["robust_metrics"]
    lines = [
        "# final-holdout-v1：串行无内容修正对照复现",
        "",
        "> 该复现使用与三级容错轮相同的逐篇检查点串行执行模式；唯一开关差异是 `max_repair_retries=0`。",
        "",
        "## 串行对照组结果",
        "",
        f"- 成功：{serial['prediction_success_count']} / {serial['ground_truth_count']}。",
        f"- 失败：{serial['prediction_missing_count']} / {serial['ground_truth_count']}。",
        "",
        "| 失败论文 | 阶段 | 字段/错误 |",
        "|---|---|---|",
    ]
    for item in report["serial_baseline_failures"]:
        error = str(item.get("error_msg", "")).replace("|", "\\|").replace("\n", "<br>")
        lines.append(
            f"| {item['filename']} | {item.get('stage', 'unknown')} | {error} |"
        )
    if not report["serial_baseline_failures"]:
        lines.append("| 无 | - | - |")
    lines.extend(
        [
            "",
            "## 与原并发对照组的状态差异",
            "",
            "| 论文 | 原并发对照 | 串行对照 |",
            "|---|---|---|",
        ]
    )
    for item in report["status_changes"]:
        lines.append(f"| {item['filename']} | {item['original_parallel']} | {item['serial_baseline']} |")
    if not report["status_changes"]:
        lines.append("| 无 | - | - |")
    lines.extend(
        [
            "",
            "## 8 字段成绩表",
            "",
            "| 字段 | 原并发无修正 | 串行无修正 | 三级容错 |",
            "|---|---:|---:|---:|",
        ]
    )
    for field in original["fields"]:
        lines.append(
            f"| {field} | {original['fields'][field]['score']:.2%} | "
            f"{serial['fields'][field]['score']:.2%} | {robust['fields'][field]['score']:.2%} |"
        )
    lines.append(
        f"| **8 字段宏平均** | {original['overall_auto_score']:.2%} | "
        f"{serial['overall_auto_score']:.2%} | {robust['overall_auto_score']:.2%} |"
    )
    definite = report["definite_fault_tolerance_files"]
    variation = report["run_variation_possible_files"]
    lines.extend(["", "## 归因结论", ""])
    lines.append(
        f"**在串行对照仍失败、而三级容错成功的论文有 {len(definite)} 篇："
        f"{', '.join(definite) if definite else '无'}；这些篇目可归因于内容修正机制。**"
    )
    lines.append(
        f"**原并发失败但串行无修正成功的论文有 {len(variation)} 篇："
        f"{', '.join(variation) if variation else '无'}；这些篇目不能排除运行间差异。**"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="串行复现 final-holdout-v1 无内容修正对照组")
    parser.add_argument("--input-dir", type=Path, default=Path("literature/optical-communications/final_holdout"))
    parser.add_argument("--serial-output", type=Path, default=Path("eval/predictions/final-holdout-v1/no_retry_serial.json"))
    parser.add_argument("--ground-truth", type=Path, default=Path("eval/ground_truth_final_holdout"))
    parser.add_argument("--original-baseline", type=Path, default=Path("eval/predictions/final-holdout-v1/no_retry.json"))
    parser.add_argument("--robust", type=Path, default=Path("eval/predictions/final-holdout-v1/with_retries.json"))
    parser.add_argument("--report", type=Path, default=Path("eval/output/final-holdout-v1/ablation-rerun.md"))
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("此命令会对 30 篇论文调用 DeepSeek；确认后加 --confirm-cost")
    if args.report.exists():
        raise FileExistsError(f"拒绝覆盖既有复现报告：{args.report}")
    files = sorted(args.input_dir.glob("*.pdf"), key=lambda path: path.name.casefold())
    if len(files) != 30:
        raise ValueError(f"预期最终留出集恰好 30 篇，当前为 {len(files)} 篇")
    run_checkpointed_predictions(
        files,
        args.serial_output,
        repair_retries=0,
        label="无内容修正重试（串行逐篇检查点复现）",
    )
    report = build_report(args.ground_truth, args.original_baseline, args.serial_output, args.robust)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_markdown(report), encoding="utf-8")
    args.report.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"串行对照复现报告：{args.report}")


if __name__ == "__main__":
    main()
