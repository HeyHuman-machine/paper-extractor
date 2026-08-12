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
3. experimental_conditions 提取论文明确给出的实验/仿真条件，例如调制格式、
   波特率、载波或太赫兹频率、传输距离与光纤类型、输入/接收光功率、采样率、
   带宽和关键器件配置。数组中只写论文明确给出的条件；缺失的条件直接省略，
   不得写“未明确给出”“根据参考文献推断”等说明；找不到时填空数组 []。
4. 找不到 main_results 时填空数组 []。
5. limitations 只能填写作者明确陈述的局限、缺点、适用边界或未来工作。
   不得根据实验条件自行推断；不得输出“未明确提及但可能……”“可能受限于……”
   等推测性内容，也不得把“作者未明确陈述局限性”当作字符串返回。
   作者未明确陈述时必须直接填 null。
6. doc_type 只能使用 Schema 中的枚举值。
7. problem 不超过 200 字，summary 不超过 400 字。
8. 指标必须保留数值、单位、条件和比较对象；证据不足时不要编造。
"""

FEW_SHOT_TEXT = """Title: Demonstration of a simplified coherent optical link
Authors: Alice Chen, Bob Li
Optics Demo 2025
Abstract: We propose a simplified receiver for short-reach optical transmission.
The experiment sends a 16-Gbaud 16QAM signal over 20 km standard single-mode
fiber at 1550 nm. At -18 dBm received optical power, the BER is 2.1×10^-3,
below the 7% HD-FEC threshold. The current setup is limited to a single
polarization; future work will evaluate polarization multiplexing."""

FEW_SHOT_RESULT: dict[str, Any] = {
    "title": "Demonstration of a simplified coherent optical link",
    "authors": ["Alice Chen", "Bob Li"],
    "year": 2025,
    "venue": "Optics Demo 2025",
    "doc_type": "journal_article",
    "problem": "降低短距光传输接收机的系统复杂度。",
    "method_name": "Simplified coherent receiver",
    "experimental_conditions": [
        "16-Gbaud 16QAM",
        "20 km standard single-mode fiber",
        "1550 nm",
        "Received optical power: -18 dBm",
    ],
    "main_results": ["BER: 2.1×10^-3, below the 7% HD-FEC threshold"],
    "limitations": "当前实验仅验证单偏振，未来将评估偏振复用。",
    "summary": "论文提出一种面向短距光传输的简化相干接收机，并在20 km标准单模光纤上验证16-Gbaud 16QAM信号。接收光功率为-18 dBm时BER达到2.1×10^-3；当前仅验证单偏振。",
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


def append_repair_message(
    messages: list[dict[str, str]],
    raw_output: str,
    stage: str,
    error_message: str,
) -> list[dict[str, str]]:
    """把上次原始输出和具体错误加入对话，要求模型只修正 JSON。

    返回新列表，不修改调用方保存的原消息，便于测试和失败诊断。
    """

    repair_prompt = f"""你上次返回的 JSON 未通过检查。
失败阶段：{stage}
具体错误：{error_message}

请根据最初提供的论文文本修正错误，并重新输出完整的 11 字段 JSON 对象。
只返回修正后的合法 JSON，不要解释，不要省略任何字段，也不要编造论文中没有的信息。"""
    return [
        *messages,
        {"role": "assistant", "content": raw_output},
        {"role": "user", "content": repair_prompt},
    ]
