"""B1：在固定 V2 预测上平行验证方法名称评分规则，不调用 API。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval.metrics import (
    AUTO_FIELDS,
    FIELD_LABELS,
    calibrated_method_match,
    calibrated_method_match_detail,
    evaluate_records,
    fuzzy_match,
    load_ground_truth,
    load_predictions,
)


def build_report(
    labels_dir: Path,
    predictions_path: Path,
) -> dict[str, Any]:
    """构建旧规则和 B1 候选规则的可复核对照报告。"""

    labels = load_ground_truth(labels_dir)
    if labels.pending_files or labels.invalid_files:
        raise ValueError("人工标注存在待确认或无效文件，不能做规则校准")
    predictions = load_predictions(predictions_path)
    baseline = evaluate_records(labels.records, predictions)
    calibrated = evaluate_records(
        labels.records,
        predictions,
        method_name_matcher=calibrated_method_match,
    )

    changed_cases = []
    for filename, truth in sorted(labels.records.items()):
        prediction = predictions.get(filename, {})
        before = fuzzy_match(truth.method_name, prediction.get("method_name"))
        after, rule = calibrated_method_match_detail(
            truth.method_name,
            prediction.get("method_name"),
        )
        if before != after:
            changed_cases.append(
                {
                    "filename": filename,
                    "before": before,
                    "after": after,
                    "rule": rule,
                    "ground_truth": truth.method_name,
                    "prediction": prediction.get("method_name"),
                }
            )

    return {
        "scope": {
            "baseline_prediction": str(predictions_path),
            "ground_truth": str(labels_dir),
            "api_called": False,
            "important_caveat": "本报告使用已暴露的 30 篇盲测集校准评分规则；仅说明旧规则的表述误判被修正，不是模型泛化能力提升。",
        },
        "rule_spec": {
            "unchanged": "标题、期刊、其他字段及方法名称旧版 0.90 fuzzy 基线均不改变。",
            "added": [
                "仅忽略括号中的解释性说明、比较对象和末尾通用后缀（method/scheme/receiver 等）。",
                "仅接受“纯缩写 ↔ 全称首字母”这一种显式缩写展开。",
                "在上述归一化后，方法名称相似度阈值从 0.90 降至 0.75。",
            ],
            "not_added": [
                "不做中文与英文的自由语义翻译。",
                "不把复合方法中遗漏的关键模块（例如仅回答 DRE）判为正确。",
                "不修改 Prompt、不调用模型、不覆盖旧分数。",
            ],
        },
        "baseline": baseline,
        "calibrated": calibrated,
        "changed_cases": changed_cases,
    }


def render_markdown(report: dict[str, Any]) -> str:
    """把 JSON 对照报告渲染为便于人工复核的 Markdown。"""

    baseline = report["baseline"]
    calibrated = report["calibrated"]
    lines = [
        "# B1 方法名称评分规则校准",
        "",
        "## 边界",
        "",
        "- 未调用 API，未改 Prompt 或抽取代码。",
        "- 使用固定的 V2 预测和已暴露的 30 篇评测集；这只是评测口径校准，不是模型能力提升或泛化结论。",
        "- 旧规则结果被完整保留。",
        "",
        "## 规则",
        "",
        "- 保留旧版 0.90 fuzzy 命中；新增仅针对括号说明、比较对象、通用后缀与“纯缩写↔全称”。",
        "- 在这些可解释归一化后，用 0.75 字符相似度判断。",
        "- 不翻译中英文，不忽略关键模块缺失。",
        "",
        "## 得分对照",
        "",
        "| 字段 | 旧规则 | B1 候选规则 | 变化 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for field in AUTO_FIELDS:
        old_score = baseline["fields"][field]["score"]
        new_score = calibrated["fields"][field]["score"]
        lines.append(
            f"| {FIELD_LABELS[field]} | {old_score:.2%} | {new_score:.2%} | {new_score - old_score:+.2%} |"
        )
    old_overall = baseline["overall_auto_score"]
    new_overall = calibrated["overall_auto_score"]
    lines.extend(
        [
            f"| 自动字段平均分 | {old_overall:.2%} | {new_overall:.2%} | {new_overall - old_overall:+.2%} |",
            "",
            "## 发生变化的论文（需人工抽查）",
            "",
            "| 文件 | 命中规则 | 标注方法 | V2 输出 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for case in report["changed_cases"]:
        lines.append(
            "| {filename} | {rule} | {ground_truth} | {prediction} |".format(**case)
        )
    if not report["changed_cases"]:
        lines.append("| 无 | - | - | - |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="B1 方法名称评测规则校准")
    parser.add_argument("--labels", type=Path, default=Path("eval/ground_truth/evaluation"))
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("eval/predictions/v2-evaluation/predictions.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("eval/output/rule-calibration-b1"))
    args = parser.parse_args()

    report = build_report(args.labels, args.predictions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "rule_calibration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "rule_calibration.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(f"旧规则：{report['baseline']['overall_auto_score']:.2%}")
    print(f"B1 候选规则：{report['calibrated']['overall_auto_score']:.2%}")
    print(f"变化案例：{len(report['changed_cases'])}")


if __name__ == "__main__":
    main()
