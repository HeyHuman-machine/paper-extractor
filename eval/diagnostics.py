"""A2-A6：固定既有预测与标注后，导出可复现的诊断指标。"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

from eval.agreement import compute_agreement
from eval.metrics import (
    _atomic_facts,
    atomic_fact_precision_recall_f1,
    fuzzy_match,
    load_ground_truth,
    load_predictions,
)


LOW_SCORE_FIELDS = ("method_name", "experimental_conditions", "main_results")
THRESHOLDS = (0.9, 0.85, 0.8, 0.75, 0.7, 0.6)


def build_diagnostics(
    ground_truth_dir: Path | str,
    predictions_path: Path | str,
) -> dict[str, Any]:
    """构建 A2-A5 所需的逐篇原始数据和聚合统计，不改动任何预测。"""

    labels = load_ground_truth(ground_truth_dir)
    if labels.pending_files or labels.invalid_files:
        raise ValueError("诊断前必须使用完整且已确认的标注集")
    predictions = load_predictions(predictions_path)
    papers: list[dict[str, Any]] = []

    for filename, truth in sorted(labels.records.items()):
        prediction = predictions.get(filename, {})
        condition = _list_score(truth.experimental_conditions, prediction.get("experimental_conditions"))
        result = _list_score(truth.main_results, prediction.get("main_results"))
        method_truth = truth.method_name
        method_prediction = prediction.get("method_name")
        papers.append(
            {
                "filename": filename,
                "method_name": {
                    "ground_truth": method_truth,
                    "prediction": method_prediction,
                    "score": float(fuzzy_match(method_truth, method_prediction, 0.9)),
                    "ground_truth_is_null": not bool(str(method_truth or "").strip()),
                    "prediction_is_null": not bool(str(method_prediction or "").strip()),
                },
                "experimental_conditions": condition,
                "main_results": result,
            }
        )

    return {
        "paper_count": len(papers),
        "prediction_file": str(predictions_path),
        "papers": papers,
        "field_summary": _field_summary(papers),
        "granularity": _granularity(papers),
        "method_sensitivity": _method_sensitivity(papers),
    }


def write_diagnostics(
    diagnosis: dict[str, Any],
    output_dir: Path | str,
    *,
    metrics_source: Path | str,
    agreement: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """写出 A2-A6 交付物；所有失败归类列保留给人工填写。"""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    raw_json = root / "per_paper_field_metrics.json"
    raw_json.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_csv = root / "per_paper_field_metrics.csv"
    _write_csv(diagnosis["papers"], raw_csv)

    precision_recall = root / "precision_recall.md"
    precision_recall.write_text(_precision_recall_markdown(diagnosis), encoding="utf-8")
    granularity = root / "granularity.md"
    granularity.write_text(_granularity_markdown(diagnosis), encoding="utf-8")
    threshold = root / "method_threshold_and_null.md"
    threshold.write_text(_method_sensitivity_markdown(diagnosis), encoding="utf-8")
    failures = root / "failure_cases.md"
    failures.write_text(_failure_cases_markdown(diagnosis), encoding="utf-8")
    rules = root / "metrics_rules.md"
    rules.write_text(_metrics_rules_markdown(Path(metrics_source)), encoding="utf-8")
    report = root / "diagnosis_report.md"
    report.write_text(_diagnosis_report_markdown(diagnosis, agreement), encoding="utf-8")
    return {
        "raw_json": raw_json,
        "raw_csv": raw_csv,
        "precision_recall": precision_recall,
        "granularity": granularity,
        "threshold": threshold,
        "failures": failures,
        "rules": rules,
        "report": report,
    }


def _list_score(expected: list[str], actual: Any) -> dict[str, Any]:
    actual_list = actual if isinstance(actual, list) else []
    precision, recall, f1 = atomic_fact_precision_recall_f1(expected, actual_list)
    return {
        "ground_truth": expected,
        "prediction": actual_list,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "ground_truth_items": len(expected),
        "prediction_items": len(actual_list),
        "ground_truth_atomic_facts": len(_atomic_facts(expected)),
        "prediction_atomic_facts": len(_atomic_facts(actual_list)),
    }


def _field_summary(papers: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for field in ("experimental_conditions", "main_results"):
        summary[field] = {
            metric: _mean([paper[field][metric] for paper in papers])
            for metric in ("precision", "recall", "f1")
        }
    summary["method_name"] = {"accuracy_at_0.90": _mean([paper["method_name"]["score"] for paper in papers])}
    return summary


def _granularity(papers: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for field in ("experimental_conditions", "main_results"):
        truth_counts = [paper[field]["ground_truth_items"] for paper in papers]
        prediction_counts = [paper[field]["prediction_items"] for paper in papers]
        ratios = [prediction / truth for prediction, truth in zip(prediction_counts, truth_counts) if truth]
        output[field] = {
            "ground_truth_mean_items": _mean(truth_counts),
            "ground_truth_median_items": statistics.median(truth_counts),
            "prediction_mean_items": _mean(prediction_counts),
            "prediction_median_items": statistics.median(prediction_counts),
            "prediction_to_truth_mean_ratio": _mean(ratios) if ratios else 0.0,
            "prediction_to_truth_median_ratio": statistics.median(ratios) if ratios else 0.0,
        }
    return output


def _method_sensitivity(papers: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for threshold in THRESHOLDS:
        correct = sum(
            fuzzy_match(paper["method_name"]["ground_truth"], paper["method_name"]["prediction"], threshold)
            for paper in papers
        )
        rows.append({"threshold": threshold, "accuracy": correct / len(papers), "correct": correct})
    null_to_null = sum(
        paper["method_name"]["ground_truth_is_null"] and paper["method_name"]["prediction_is_null"]
        for paper in papers
    )
    truth_null = sum(paper["method_name"]["ground_truth_is_null"] for paper in papers)
    prediction_null = sum(paper["method_name"]["prediction_is_null"] for paper in papers)
    return {
        "thresholds": rows,
        "ground_truth_null_count": truth_null,
        "prediction_null_count": prediction_null,
        "null_to_null_count": null_to_null,
        "null_to_null_share": null_to_null / len(papers),
    }


def _write_csv(papers: list[dict[str, Any]], path: Path) -> None:
    columns = [
        "filename", "field", "precision", "recall", "f1", "score", "ground_truth", "prediction",
        "ground_truth_items", "prediction_items", "ground_truth_atomic_facts", "prediction_atomic_facts",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for paper in papers:
            method = paper["method_name"]
            writer.writerow({
                "filename": paper["filename"], "field": "method_name", "score": method["score"],
                "ground_truth": method["ground_truth"], "prediction": method["prediction"],
            })
            for field in ("experimental_conditions", "main_results"):
                item = paper[field]
                writer.writerow({
                    "filename": paper["filename"], "field": field, "precision": item["precision"],
                    "recall": item["recall"], "f1": item["f1"],
                    "ground_truth": json.dumps(item["ground_truth"], ensure_ascii=False),
                    "prediction": json.dumps(item["prediction"], ensure_ascii=False),
                    "ground_truth_items": item["ground_truth_items"], "prediction_items": item["prediction_items"],
                    "ground_truth_atomic_facts": item["ground_truth_atomic_facts"],
                    "prediction_atomic_facts": item["prediction_atomic_facts"],
                })


def _precision_recall_markdown(diagnosis: dict[str, Any]) -> str:
    summary = diagnosis["field_summary"]
    lines = ["# A2：Precision / Recall / F1", "", f"> 固定 V2 预测，样本：{diagnosis['paper_count']} 篇。", "", "| 字段 | Precision | Recall | F1 |", "|---|---:|---:|---:|"]
    for field in ("experimental_conditions", "main_results"):
        value = summary[field]
        lines.append(f"| {field} | {value['precision']:.2%} | {value['recall']:.2%} | {value['f1']:.2%} |")
    lines += ["", "逐篇明细见 `per_paper_field_metrics.csv` 与 `per_paper_field_metrics.json`。", "", "解读：Precision 低偏向多抽/错抽；Recall 低偏向漏抽或标注粒度更细。两者都需结合 A3 和 A5 判断。"]
    return "\n".join(lines) + "\n"


def _granularity_markdown(diagnosis: dict[str, Any]) -> str:
    lines = ["# A3：切分粒度统计", "", "| 字段 | 标注平均条数 | 标注中位数 | 模型平均条数 | 模型中位数 | 模型/标注平均比 |", "|---|---:|---:|---:|---:|---:|"]
    for field, value in diagnosis["granularity"].items():
        lines.append(f"| {field} | {value['ground_truth_mean_items']:.2f} | {value['ground_truth_median_items']:.2f} | {value['prediction_mean_items']:.2f} | {value['prediction_median_items']:.2f} | {value['prediction_to_truth_mean_ratio']:.2f} |")
    lines += ["", "比值显著偏离 1 时，列表如何拆分本身就是失分来源；不能把所有低分直接归咎于模型。"]
    return "\n".join(lines) + "\n"


def _method_sensitivity_markdown(diagnosis: dict[str, Any]) -> str:
    sensitivity = diagnosis["method_sensitivity"]
    lines = ["# A4：方法名称阈值与 null 敏感性", "", "| 模糊匹配阈值 | 正确篇数 | 准确率 |", "|---:|---:|---:|"]
    for row in sensitivity["thresholds"]:
        lines.append(f"| {row['threshold']:.2f} | {row['correct']} | {row['accuracy']:.2%} |")
    lines += ["", "| null 统计 | 数量 | 占比 |", "|---|---:|---:|", f"| 标注为 null | {sensitivity['ground_truth_null_count']} | {sensitivity['ground_truth_null_count']/diagnosis['paper_count']:.2%} |", f"| 模型为 null | {sensitivity['prediction_null_count']} | {sensitivity['prediction_null_count']/diagnosis['paper_count']:.2%} |", f"| null → null | {sensitivity['null_to_null_count']} | {sensitivity['null_to_null_share']:.2%} |", "", "说明：这里只改变评分阈值，不重跑模型、不改抽取逻辑。"]
    return "\n".join(lines) + "\n"


def _failure_cases_markdown(diagnosis: dict[str, Any], limit: int = 15) -> str:
    lines = ["# A5：低分失败案例（待人工归类）", "", "> 失败归类请从：模型漏抽 / 模型错抽 / 措辞不同但等价 / 切分粒度不同 / 标注本身有歧义 中选择。", ""]
    for field in LOW_SCORE_FIELDS:
        rows = sorted(diagnosis["papers"], key=lambda paper: paper[field]["score"] if field == "method_name" else paper[field]["f1"])[:limit]
        lines += [f"## {field}", "", "| 论文 | 人工标注 | 模型输出 | 得分 | 失败归类 |", "|---|---|---|---:|---|"]
        for paper in rows:
            item = paper[field]
            score = item["score"] if field == "method_name" else item["f1"]
            truth = _table_text(item["ground_truth"])
            prediction = _table_text(item["prediction"])
            lines.append(f"| {paper['filename']} | {truth} | {prediction} | {score:.2%} |  |")
        lines.append("")
    return "\n".join(lines) + "\n"


def _metrics_rules_markdown(metrics_path: Path) -> str:
    source = metrics_path.read_text(encoding="utf-8")
    return "\n".join([
        "# A6：当前评测规则代码审查", "", "## 规则对应关系", "", "- `fuzzy_match`：标题、期刊、方法名称经归一化后用 `SequenceMatcher`，默认阈值 0.90。", "- `atomic_fact_precision_recall_f1`：实验条件与主要结果先提取数值+单位、调制格式、BER/OSNR 等原子事实，再计算集合 P/R/F1。", "- 原子事实的优点是降低“同一句拆成几条”的影响；限制是未覆盖的同义词和语义等价表达仍可能失分。", "", "## 完整 `eval/metrics.py`", "", "```python", source.rstrip(), "```", "",
    ])


def _diagnosis_report_markdown(
    diagnosis: dict[str, Any], agreement: dict[str, Any] | None = None
) -> str:
    condition = diagnosis["field_summary"]["experimental_conditions"]
    result = diagnosis["field_summary"]["main_results"]
    method = diagnosis["method_sensitivity"]
    lines = [
        "# 阶段 A 诊断报告（A2-A6 初版）", "", "> 本报告固定既有 V2 预测，不改提示词、不改抽取程序。A1 的独立 AI 复核报告另见 `agreement.md`。", "",
    ]
    if agreement:
        lines += [
            "## A1：独立 AI 复核（8 篇）", "",
            f"- 方法名称一致性：{agreement['fields']['method_name']['score']:.2%}。",
            f"- 实验条件一致性：{agreement['fields']['experimental_conditions']['f1']:.2%} F1。",
            f"- 主要结果一致性：{agreement['fields']['main_results']['f1']:.2%} F1。",
            "- 这不是人类一致性，不能用于估计严格的人类标注上限。", "",
        ]
    lines += [
        "## 已观察到的信号", "",
        f"- 实验条件：Precision {condition['precision']:.2%}、Recall {condition['recall']:.2%}、F1 {condition['f1']:.2%}。",
        f"- 主要结果：Precision {result['precision']:.2%}、Recall {result['recall']:.2%}、F1 {result['f1']:.2%}。",
        f"- 方法名称在阈值 0.90 下为 {method['thresholds'][0]['accuracy']:.2%}；null→null 为 {method['null_to_null_share']:.2%}。", "",
        "## 当前结论边界", "",
        "- 低 Recall 既可能是模型漏抽，也可能是标注记录了更多事实；A3 的条数比与 A5 的逐例归类用于区分。",
        "- A1 是独立 AI 复核，不是严格的人类自一致性；它只能作为标注歧义的预警，不能替代人工上限估计。",
        "- 下一阶段 B 之前，应先完成人工填写 `failure_cases.md` 的归类列，并据此为规则修改写出可审计理由。", "",
    ]
    return "\n".join(lines)


def _table_text(value: Any) -> str:
    if isinstance(value, list):
        text = "<br>".join(str(item) for item in value)
    else:
        text = str(value or "null")
    return text.replace("|", "\\|").replace("\n", " ")


def _mean(values: list[float | int]) -> float:
    return sum(values) / len(values) if values else 0.0
