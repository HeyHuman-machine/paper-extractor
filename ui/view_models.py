"""把 M7 JSON 转换成适合 Streamlit 表格展示的数据。"""

from __future__ import annotations

from datetime import datetime
from typing import Any


RESULT_COLUMNS = {
    "filename": "文件名",
    "title": "标题",
    "authors": "作者",
    "year": "年份",
    "venue": "期刊 / 会议",
    "method_name": "方法名称",
    "experimental_conditions": "实验条件",
    "main_results": "主要结果",
    "limitations": "局限性",
    "retry_count": "重试",
    "tokens": "Token",
    "latency_ms": "耗时(ms)",
}

RESULT_SUMMARY_COLUMNS = {
    "filename": "文件名",
    "title": "标题",
    "year": "年份",
    "venue": "期刊 / 会议",
    "method_name": "方法名称",
    "retry_count": "重试",
    "tokens": "Token",
}


def task_rows(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成历史任务表，成功率由后端计数计算。"""

    rows: list[dict[str, Any]] = []
    for task in tasks:
        total = task["total_files"]
        success_rate = task["success_count"] / total if total else 0
        rows.append(
            {
                "任务 ID": task["id"],
                "完成时间": _display_time(task.get("finished_at") or task["created_at"]),
                "文件数": total,
                "成功": task["success_count"],
                "失败": task["fail_count"],
                "成功率": f"{success_rate:.0%}",
                "耗时(s)": round(task["duration_ms"] / 1000, 2),
                "Token": task["total_tokens"],
            }
        )
    return rows


def result_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """列表字段用换行文本展示，保持表格可读。"""

    rows: list[dict[str, Any]] = []
    for result in results:
        row: dict[str, Any] = {}
        for field, label in RESULT_COLUMNS.items():
            value = result.get(field)
            row[label] = "\n".join(value) if isinstance(value, list) else value
        rows.append(row)
    return rows


def result_summary_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {label: result.get(field) for field, label in RESULT_SUMMARY_COLUMNS.items()}
        for result in results
    ]


def failure_rows(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "文件名": item["filename"],
            "失败阶段": item["stage"],
            "错误类型": item["error_type"],
            "错误信息": item["error_msg"],
            "重试次数": item["retry_count"],
        }
        for item in failures
    ]


def _display_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
