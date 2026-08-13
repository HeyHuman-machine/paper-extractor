"""M9 报告生成：Markdown、JSON 和无需新依赖的 PNG 柱状图。"""

from __future__ import annotations

import json
import struct
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.metrics import AUTO_FIELDS, FIELD_LABELS, GroundTruthSet, evaluate_records


_CHART_LABELS = {
    "title": "TITLE",
    "authors": "AUTHORS",
    "year": "YEAR",
    "venue": "VENUE",
    "doc_type": "DOC TYPE",
    "method_name": "METHOD",
    "experimental_conditions": "CONDITIONS",
    "main_results": "RESULTS",
}


def build_comparison(
    labels: GroundTruthSet,
    baseline_predictions: dict[str, dict[str, Any]],
    robust_predictions: dict[str, dict[str, Any]],
    *,
    baseline_label: str = "无内容修正重试",
    comparison_label: str = "三级容错",
) -> dict[str, Any]:
    """生成两轮结果与百分点提升；不把相对百分比和百分点混为一谈。"""

    baseline = evaluate_records(labels.records, baseline_predictions)
    robust = evaluate_records(labels.records, robust_predictions)
    absolute_delta = robust["overall_auto_score"] - baseline["overall_auto_score"]
    relative_improvement = (
        absolute_delta / baseline["overall_auto_score"]
        if baseline["overall_auto_score"]
        else None
    )
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "confirmed_labels": len(labels.records),
        "pending_labels": len(labels.pending_files),
        "invalid_label_files": labels.invalid_files,
        "baseline": baseline,
        "with_retries": robust,
        "baseline_label": baseline_label,
        "comparison_label": comparison_label,
        "overall_delta": absolute_delta,
        "relative_improvement": relative_improvement,
    }


def write_report(report: dict[str, Any], output_dir: Path | str) -> dict[str, Path]:
    """一次写出人读 Markdown、程序读 JSON 和浏览器可显示 PNG。"""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    markdown_path = directory / "report.md"
    chart_path = directory / "field_scores.png"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    chart_path.write_bytes(_png_chart(report))
    return {"json": json_path, "markdown": markdown_path, "chart": chart_path}


def _markdown(report: dict[str, Any]) -> str:
    baseline = report["baseline"]
    robust = report["with_retries"]
    baseline_label = report.get("baseline_label", "无内容修正重试")
    comparison_label = report.get("comparison_label", "三级容错")
    lines = [
        "# PaperExtractor M9 评测报告",
        "",
        f"> 生成时间：{report['generated_at']}  ",
        f"> 已确认人工标注：{report['confirmed_labels']} 篇  ",
        "> 自动总分仅包含 8 个客观字段；3 个自由文本字段不自动评分。",
        "",
        "## 核心对比",
        "",
        "| 配置 | 成功论文 | 抽取成功率 | 8 字段宏平均分 |",
        "|---|---:|---:|---:|",
        _round_row(baseline_label, baseline),
        _round_row(comparison_label, robust),
        "",
        f"- 绝对提升：**{report['overall_delta'] * 100:+.2f} 个百分点**。",
    ]
    relative = report.get("relative_improvement")
    if relative is not None:
        lines.append(f"- 相对提升：**{relative * 100:+.2f}%**。")
    lines.extend(
        [
            "",
            "## 各字段原始结果",
            "",
            f"| 字段 | 规则 | {baseline_label} | {comparison_label} | 差值（百分点） |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for field in AUTO_FIELDS:
        before = baseline["fields"][field]
        after = robust["fields"][field]
        lines.append(
            f"| {FIELD_LABELS[field]} | {_rule_label(before['kind'])} | "
            f"{before['score']:.2%} | {after['score']:.2%} | "
            f"{(after['score'] - before['score']) * 100:+.2f} |"
        )
    lines.extend(
        [
            "",
            "## 不自动评分的字段",
            "",
            "`problem`、`limitations`、`summary` 属于自由文本。多个不同表述可能都正确，"
            "字符相似度不能代表事实正确，因此留给人工抽样评分，不并入自动总分。",
            "",
            "## 解释边界",
            "",
            "- 这份报告衡量当前标注集和当前模型配置，不代表所有论文领域。",
            "- 两组配置除本次声明的自变量外应保持一致；HTTP 网络重试始终保持一致。",
            "- 同一模型也可能有轻微随机性；报告保留原始预测 JSON 以便复查。",
        ]
    )
    return "\n".join(lines) + "\n"


def _round_row(label: str, result: dict[str, Any]) -> str:
    return (
        f"| {label} | {result['prediction_success_count']}/"
        f"{result['ground_truth_count']} | {result['extraction_success_rate']:.2%} | "
        f"{result['overall_auto_score']:.2%} |"
    )


def _rule_label(kind: str) -> str:
    return {
        "exact": "精确匹配",
        "fuzzy": "归一化模糊匹配",
        "set": "集合宏 F1",
        "atomic_fact_set": "原子事实集合 F1",
    }[kind]


def _png_chart(report: dict[str, Any]) -> bytes:
    """用标准库直接生成 PNG，避免为一张图增加 Matplotlib 依赖。"""

    width, height = 900, 540
    pixels = bytearray((247, 249, 252) * width * height)

    def rectangle(x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        x_end = min(width, x + max(0, w))
        y_end = min(height, y + max(0, h))
        row = bytes(color) * max(0, x_end - x)
        for current_y in range(max(0, y), y_end):
            start = (current_y * width + max(0, x)) * 3
            pixels[start : start + len(row)] = row

    left, top, bar_max, row_gap = 235, 50, 560, 58
    baseline = report["baseline"]["fields"]
    robust = report["with_retries"]["fields"]
    for tick in range(5):
        x = left + round(bar_max * tick / 4)
        rectangle(x, 35, 1, 472, (220, 229, 236))
    for index, field in enumerate(AUTO_FIELDS):
        y = top + index * row_gap
        before = baseline[field]["score"]
        after = robust[field]["score"]
        _draw_text(pixels, width, height, 18, y + 4, _CHART_LABELS[field], (48, 68, 90), 2)
        rectangle(left, y, round(bar_max * before), 16, (143, 168, 232))
        rectangle(left, y + 22, round(bar_max * after), 16, (64, 185, 154))
        _draw_text(pixels, width, height, 810, y + 2, f"{before * 100:.0f}%", (82, 101, 122), 2)
        _draw_text(pixels, width, height, 810, y + 24, f"{after * 100:.0f}%", (25, 133, 104), 2)
    _draw_text(pixels, width, height, 235, 515, "NO RETRY", (83, 104, 126), 2)
    rectangle(205, 514, 18, 10, (143, 168, 232))
    _draw_text(pixels, width, height, 450, 515, "WITH RETRIES", (25, 133, 104), 2)
    rectangle(420, 514, 18, 10, (64, 185, 154))

    raw = b"".join(b"\x00" + pixels[row * width * 3 : (row + 1) * width * 3] for row in range(height))
    signature = b"\x89PNG\r\n\x1a\n"
    return signature + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + _png_chunk(b"IDAT", zlib.compress(raw, 9)) + _png_chunk(b"IEND", b"")


_FONT = {
    "A": "011101000110001111111000110001", "B": "111101000111110100011000111110",
    "C": "011111000010000100001000001111", "D": "111101000110001100011000111110",
    "E": "111111000011110100001000011111", "F": "111111000011110100001000010000",
    "H": "100011000111111100011000110001", "I": "111110010000100001000010011111",
    "L": "100001000010000100001000011111", "M": "100011101110101100011000110001",
    "N": "100011100110101100111000110001", "O": "011101000110001100011000101110",
    "P": "111101000110001111101000010000", "R": "111101000110001111101001010001",
    "S": "011111000001110000011000111110", "T": "111110010000100001000010000100",
    "U": "100011000110001100011000101110", "V": "100011000110001100010101000100",
    "W": "100011000110101101011010101010", "X": "100011000101010001000101010001",
    "Y": "100011000101010001000010000100", "_": "000000000000000000000000011111",
    " ": "000000000000000000000000000000", "%": "110011101000100010001011001100",
    "0": "011101000110011101011100101110", "1": "001000110000100001000010001110",
    "2": "011101000100001001100100011111", "3": "111100000100110000011000111110",
    "4": "000100011001010100101111100010", "5": "111111000011110000011000111110",
    "6": "011101000010000111101000101110", "7": "111110000100010001000100001000",
    "8": "011101000101110100011000101110", "9": "011101000110001011110000101110",
}


def _draw_text(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    text: str,
    color: tuple[int, int, int],
    scale: int,
) -> None:
    for character in text:
        glyph = _FONT.get(character, _FONT[" "])
        for row in range(6):
            for column in range(5):
                if glyph[row * 5 + column] == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            px, py = x + column * scale + dx, y + row * scale + dy
                            if 0 <= px < width and 0 <= py < height:
                                start = (py * width + px) * 3
                                pixels[start : start + 3] = bytes(color)
        x += 6 * scale


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)
