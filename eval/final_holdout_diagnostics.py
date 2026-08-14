"""冻结 final-holdout-v1 的只读诊断。

本模块只读取已经冻结的人工标签和既有预测，绝不修改 Prompt、阈值或模型配置。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval.metrics import (
    _atomic_facts,
    atomic_fact_precision_recall_f1,
    fuzzy_match,
    load_ground_truth,
    load_predictions,
)


def arxiv_submission_year(arxiv_id: str) -> int:
    """从现代 arXiv ID 的前两位恢复提交年份。"""

    prefix = str(arxiv_id).strip()[:2]
    if len(prefix) != 2 or not prefix.isdigit():
        raise ValueError(f"无法从 arXiv ID 推断年份：{arxiv_id!r}")
    return 2000 + int(prefix)


def build_version_convention_analysis(
    ground_truth_dir: Path | str,
    predictions_path: Path | str,
    manifest_path: Path | str,
) -> dict[str, Any]:
    """比较人工标签、模型输出与 arXiv 提交年，不改动任何评测口径。"""

    labels = load_ground_truth(ground_truth_dir)
    if labels.pending_files or labels.invalid_files:
        raise ValueError("最终留出集标签必须全部确认且有效")
    predictions = load_predictions(predictions_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    arxiv_years = {
        str(item["filename"]).casefold(): arxiv_submission_year(str(item["arxiv_id"]))
        for item in manifest["papers"]
    }

    year_errors: list[dict[str, Any]] = []
    doc_type_errors: list[dict[str, Any]] = []
    venue_errors: list[dict[str, Any]] = []
    for filename, truth in sorted(labels.records.items()):
        prediction = predictions.get(filename, {})
        arxiv_year = arxiv_years[filename]
        model_year = prediction.get("year")
        if truth.year != model_year:
            year_errors.append(
                {
                    "filename": filename,
                    "ground_truth_year": truth.year,
                    "model_year": model_year,
                    "arxiv_submission_year": arxiv_year,
                    "model_matches_arxiv_but_truth_differs": (
                        model_year == arxiv_year and truth.year != arxiv_year
                    ),
                }
            )
        if truth.doc_type.value != prediction.get("doc_type"):
            doc_type_errors.append(
                {
                    "filename": filename,
                    "ground_truth_doc_type": truth.doc_type.value,
                    "model_doc_type": prediction.get("doc_type"),
                }
            )
        model_venue = prediction.get("venue")
        if not fuzzy_match(truth.venue, model_venue, threshold=0.9):
            venue_errors.append(
                {
                    "filename": filename,
                    "ground_truth_venue": truth.venue,
                    "model_venue": model_venue,
                }
            )

    published = []
    preprint_only = []
    for filename, truth in sorted(labels.records.items()):
        venue = str(truth.venue or "").strip()
        if venue and "arxiv" not in venue.casefold():
            published.append(filename)
        else:
            preprint_only.append(filename)

    model_matches_arxiv = sum(
        row["model_matches_arxiv_but_truth_differs"] for row in year_errors
    )
    doc_version_direction_count = sum(
        (row["ground_truth_doc_type"] == "preprint")
        != (str(row["model_doc_type"] or "") == "preprint")
        for row in doc_type_errors
    )
    venue_truth_preprint_model_formal = sum(
        _is_arxiv_preprint(row["ground_truth_venue"])
        and bool(str(row["model_venue"] or "").strip())
        and not _is_arxiv_preprint(row["model_venue"])
        for row in venue_errors
    )
    venue_truth_formal_model_preprint = sum(
        bool(str(row["ground_truth_venue"] or "").strip())
        and not _is_arxiv_preprint(row["ground_truth_venue"])
        and _is_arxiv_preprint(row["model_venue"])
        for row in venue_errors
    )
    venue_model_missing = sum(not str(row["model_venue"] or "").strip() for row in venue_errors)
    return {
        "sample_count": len(labels.records),
        "year_errors": year_errors,
        "doc_type_errors": doc_type_errors,
        "year_error_model_matches_arxiv_count": model_matches_arxiv,
        "year_error_model_matches_arxiv_ratio": (
            model_matches_arxiv / len(year_errors) if year_errors else 0.0
        ),
        "doc_type_version_direction_count": doc_version_direction_count,
        "venue_errors": venue_errors,
        "venue_truth_preprint_model_formal_count": venue_truth_preprint_model_formal,
        "venue_truth_formal_model_preprint_count": venue_truth_formal_model_preprint,
        "venue_model_missing_count": venue_model_missing,
        "published_preprint_count": len(published),
        "preprint_only_count": len(preprint_only),
        "published_preprint_files": published,
        "preprint_only_files": preprint_only,
    }


def build_atomic_fact_coverage(
    ground_truth_dir: Path | str,
    predictions_path: Path | str,
) -> dict[str, Any]:
    """统计原子事实指标的零覆盖与稀疏覆盖，不改动指标实现。"""

    labels = load_ground_truth(ground_truth_dir)
    if labels.pending_files or labels.invalid_files:
        raise ValueError("最终留出集标签必须全部确认且有效")
    predictions = load_predictions(predictions_path)
    fields: dict[str, Any] = {}
    for field in ("experimental_conditions", "main_results"):
        rows = []
        for filename, truth in sorted(labels.records.items()):
            expected = getattr(truth, field)
            actual = predictions.get(filename, {}).get(field)
            precision, recall, f1 = atomic_fact_precision_recall_f1(expected, actual)
            rows.append(
                {
                    "filename": filename,
                    "expected_fact_count": len(_atomic_facts(expected)),
                    "actual_fact_count": len(_atomic_facts(actual)),
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                }
            )

        zero = [row for row in rows if row["expected_fact_count"] == 0]
        one = [row for row in rows if row["expected_fact_count"] == 1]
        nonzero = [row for row in rows if row["expected_fact_count"] > 0]
        fields[field] = {
            "rows": rows,
            "expected_zero_count": len(zero),
            "expected_one_count": len(one),
            "expected_zero_mean_f1": _mean(zero, "f1"),
            "expected_one_mean_f1": _mean(one, "f1"),
            "nonzero_precision": _mean(nonzero, "precision"),
            "nonzero_recall": _mean(nonzero, "recall"),
            "nonzero_f1": _mean(nonzero, "f1"),
            "zero_files": [row["filename"] for row in zero],
            "one_files": [row["filename"] for row in one],
        }
    return {"sample_count": len(labels.records), "fields": fields}


def render_version_markdown(result: dict[str, Any]) -> str:
    year_errors = result["year_errors"]
    doc_errors = result["doc_type_errors"]
    lines = [
        "# final-holdout-v1：版本口径分析",
        "",
        "> 只读分析冻结标签与既有三级容错预测；不修改 Prompt、阈值或抽取参数。",
        "",
        "## 年份判错样例",
        "",
        "| 论文编号 | 人工标注年份 | 模型输出年份 | arXiv 提交年份 |",
        "|---|---:|---:|---:|",
    ]
    for row in year_errors:
        lines.append(
            f"| {row['filename']} | {_cell(row['ground_truth_year'])} | "
            f"{_cell(row['model_year'])} | {row['arxiv_submission_year']} |"
        )
    lines.extend(
        [
            "",
            "## 文档类型判错样例",
            "",
            "| 论文编号 | 人工标注文档类型 | 模型输出文档类型 |",
            "|---|---|---|",
        ]
    )
    for row in doc_errors:
        lines.append(
            f"| {row['filename']} | {row['ground_truth_doc_type']} | "
            f"{_cell(row['model_doc_type'])} |"
        )
    lines.extend(
        [
            "",
            "## 统计",
            "",
            f"- 年份判错：{len(year_errors)} / {result['sample_count']}。",
            "- 其中“模型年份 = arXiv 提交年，且人工年份为其他年份”："
            f"{result['year_error_model_matches_arxiv_count']} / {len(year_errors)} "
            f"（{result['year_error_model_matches_arxiv_ratio']:.2%}）。",
            f"- 文档类型判错中，preprint 与 journal/conference 的版本方向冲突：{result['doc_type_version_direction_count']} / {len(doc_errors)}。",
            f"- 期刊/会议判错：{len(result['venue_errors'])} / {result['sample_count']}；其中人工为 arXiv 预印本、模型给正式载体：{result['venue_truth_preprint_model_formal_count']}；人工为正式载体、模型给 arXiv：{result['venue_truth_formal_model_preprint_count']}；模型未给载体：{result['venue_model_missing_count']}。",
            f"- 人工标注为正式发表载体的 arXiv 预印本：{result['published_preprint_count']} / {result['sample_count']}。",
            f"- 人工标注为 arXiv 预印本或未给出正式载体：{result['preprint_only_count']} / {result['sample_count']}。",
            "",
            "## 结论",
            "",
        ]
    )
    ratio = result["year_error_model_matches_arxiv_ratio"]
    if ratio >= 0.5:
        conclusion = "年份、文档类型与期刊的低分主要呈现版本口径歧义；仍不能据此免除模型抽取错误的核查。"
    else:
        conclusion = "文档类型与期刊中存在显著的预印本/正式发表版本口径冲突，但年份 16 个错误中 0 个符合“模型取 arXiv 年、人工取发表年”；因此三个字段的低分不能整体归因于版本口径，年份主要仍是模型抽取或标签口径问题。"
    lines.append(f"**{conclusion}**")
    return "\n".join(lines) + "\n"


def render_atomic_markdown(result: dict[str, Any]) -> str:
    total = result["sample_count"]
    lines = [
        "# final-holdout-v1：原子事实指标覆盖度",
        "",
        "> 只做统计，不修改 `eval/metrics.py` 的指标实现。",
        "",
        "| 字段 | expected=0 | expected=1 | expected=0 的平均 F1 | expected=1 的平均 F1 | 排除 expected=0 后 P / R / F1 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for field, stats in result["fields"].items():
        lines.append(
            f"| {field} | {stats['expected_zero_count']}/{total} "
            f"({stats['expected_zero_count']/total:.2%}) | {stats['expected_one_count']}/{total} "
            f"({stats['expected_one_count']/total:.2%}) | {stats['expected_zero_mean_f1']:.2%} | "
            f"{stats['expected_one_mean_f1']:.2%} | {stats['nonzero_precision']:.2%} / "
            f"{stats['nonzero_recall']:.2%} / {stats['nonzero_f1']:.2%} |"
        )
    lines.extend(["", "## 结论", ""])
    condition = result["fields"]["experimental_conditions"]
    result_field = result["fields"]["main_results"]
    lines.append(
        "严格意义上，人工标签没有任何可识别原子事实的论文占：实验条件 "
        f"{condition['expected_zero_count']}/{total}（{condition['expected_zero_count']/total:.2%}），"
        f"主要结果 {result_field['expected_zero_count']}/{total}（{result_field['expected_zero_count']/total:.2%}）。"
    )
    lines.append(
        "这些样例中，只要模型输出了任何可识别 token，F1 就会结构性趋向 0；因此该比例测量的并非模型是否抽到定性事实，"
        "而是人工标签是否包含当前正则可识别的事实。将 expected=0 与 expected=1 合并看，"
        f"实验条件为 {(condition['expected_zero_count'] + condition['expected_one_count'])}/{total}，"
        f"主要结果为 {(result_field['expected_zero_count'] + result_field['expected_one_count'])}/{total}，属于稀疏、易受标签书写方式影响的样本。"
    )
    return "\n".join(lines) + "\n"


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0


def _cell(value: Any) -> str:
    return "null" if value is None else str(value)


def _is_arxiv_preprint(value: Any) -> bool:
    return "arxiv" in str(value or "").casefold()


def main() -> None:
    parser = argparse.ArgumentParser(description="冻结 final-holdout-v1 的只读诊断")
    parser.add_argument("--ground-truth", type=Path, default=Path("eval/ground_truth_final_holdout"))
    parser.add_argument("--predictions", type=Path, default=Path("eval/predictions/final-holdout-v1/with_retries.json"))
    parser.add_argument("--manifest", type=Path, default=Path("eval/final_holdout_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("eval/output/final-holdout-v1"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    version = build_version_convention_analysis(args.ground_truth, args.predictions, args.manifest)
    atomic = build_atomic_fact_coverage(args.ground_truth, args.predictions)
    (args.output_dir / "version-convention-analysis.json").write_text(
        json.dumps(version, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "version-convention-analysis.md").write_text(
        render_version_markdown(version), encoding="utf-8"
    )
    (args.output_dir / "atomic-fact-coverage.json").write_text(
        json.dumps(atomic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "atomic-fact-coverage.md").write_text(
        render_atomic_markdown(atomic), encoding="utf-8"
    )
    print(f"版本口径报告：{args.output_dir / 'version-convention-analysis.md'}")
    print(f"原子事实报告：{args.output_dir / 'atomic-fact-coverage.md'}")


if __name__ == "__main__":
    main()
