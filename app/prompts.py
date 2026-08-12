"""论文 11 字段结构化抽取 Prompt。"""

from __future__ import annotations

import json
from typing import Any

from app.models import PaperRecord


SYSTEM_PROMPT = """你是严谨的学术论文信息抽取助手。
请只依据用户给出的论文文本抽取信息，禁止使用外部知识补全或猜测。
你必须只返回一个合法 JSON 对象，不要返回 Markdown 代码块、解释或额外文字。
输出必须符合下面的 JSON Schema：
{schema}

填写规则：
1. title、problem、summary 必须是非空字符串。
2. authors 至少一项；找不到 year、venue、method_name、limitations 时填 null。
3. 找不到 datasets 或 main_results 时填空数组 []。
4. doc_type 只能使用 Schema 中的枚举值。
5. problem 不超过 200 字，summary 不超过 400 字。
6. 指标必须保留数值、单位、条件和比较对象；证据不足时不要编造。
"""

FEW_SHOT_TEXT = """Title: TinySort: A Compact Sorting Method
Authors: Alice Chen, Bob Li
Proceedings of DemoConf 2025
Abstract: We reduce memory use when sorting sensor records. TinySort uses bounded
buckets and is evaluated on SensorSet. It reaches 94.2% accuracy using 32 MB,
but has only been tested on fixed-length records. Conclusion: TinySort is a
compact method for constrained devices."""

FEW_SHOT_RESULT: dict[str, Any] = {
    "title": "TinySort: A Compact Sorting Method",
    "authors": ["Alice Chen", "Bob Li"],
    "year": 2025,
    "venue": "DemoConf 2025",
    "doc_type": "conference_paper",
    "problem": "降低受限设备排序传感器记录时的内存占用。",
    "method_name": "TinySort",
    "datasets": ["SensorSet"],
    "main_results": ["Accuracy: 94.2% using 32 MB"],
    "limitations": "仅在定长记录上进行了测试。",
    "summary": "论文提出 TinySort，通过有界桶降低传感器记录排序的内存占用。该方法在 SensorSet 上以 32 MB 内存取得 94.2% 准确率，但目前仅验证了定长记录。",
}


def build_extraction_messages(paper_text: str) -> list[dict[str, str]]:
    """把论文文本包装成 OpenAI 兼容的消息列表。"""

    cleaned_text = paper_text.strip()
    if not cleaned_text:
        raise ValueError("paper_text 不能为空")

    schema = json.dumps(
        PaperRecord.model_json_schema(), ensure_ascii=False, indent=2
    )
    example_json = json.dumps(
        FEW_SHOT_RESULT, ensure_ascii=False, indent=2
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema)},
        {
            "role": "user",
            "content": f"示例论文文本：\n{FEW_SHOT_TEXT}",
        },
        {"role": "assistant", "content": example_json},
        {
            "role": "user",
            "content": f"请从下面的论文文本中抽取 JSON：\n\n{cleaned_text}",
        },
    ]
