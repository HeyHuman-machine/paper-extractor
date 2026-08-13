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
3. experimental_conditions 提取论文明确给出的实验/仿真条件。每个数组元素只能表达
   一个原子事实，统一使用“字段名: 值”的英文格式，例如：
   "modulation: 16QAM"、"baud_rate: 16 Gbaud"、"fiber_length: 20 km"、
   "wavelength: 1550 nm"、"received_optical_power: -18 dBm"、
   "carrier_frequency: 0.3 THz"。不要把多个条件合并到一条；没有明确给出的条件
   直接省略，不得写“未明确给出”“根据参考文献推断”等说明；找不到时填空数组 []。
4. main_results 中每个数组元素也只能表达一个可核对的原子结果，统一使用
   “指标: 数值 | 条件: ...”格式，例如：
   "BER: 2.1e-3 | condition: received_optical_power -18 dBm"、
   "BER: below 3.8e-3 HD-FEC | condition: 10 km SSMF"。必须保留指标、数值、
   单位、阈值和适用条件；同一条不得堆叠多个独立实验结果；找不到时填空数组 []。
5. limitations 只能填写作者明确陈述的局限、缺点、适用边界或未来工作。
   不得根据实验条件自行推断；不得输出“未明确提及但可能……”“可能受限于……”
   等推测性内容，也不得把“作者未明确陈述局限性”当作字符串返回。
   作者未明确陈述时必须直接填 null。
6. doc_type 只能使用 Schema 中的枚举值。
7. problem 不超过 200 字，summary 不超过 400 字。
8. 指标必须保留数值、单位、条件和比较对象；证据不足时不要编造。
"""

V4_EVIDENCE_RULES = """
V4 取证规则：用户文本带有“论文开头”“方法命名证据”“实验 / 仿真 / 结果证据”和
“论文结尾”标签。标签表示原文来源，不是需要输出的内容。
1. title、authors、year、venue 优先依据“论文开头”；method_name 仅可依据标题或
   “方法命名证据”中作者明确命名的短语。若只有普通技术描述，填 null。
2. experimental_conditions 只列入决定本论文实验/仿真配置的量化设置：调制格式、
   波特率/比特率、传输距离与链路、频率/波长、接收或输入功率、采样率、明确算法
   参数。不要把普通器件介绍、通用背景参数或未出现在实验/仿真证据中的规格写入。
3. main_results 只列入“实验 / 仿真 / 结果证据”中可量化或有阈值/比较对象的结论，
   优先 BER、FEC 阈值、接收灵敏度/功率罚、传输距离、容量和算法迭代收益。每条必须
   保留数值或明确比较和适用条件；没有可核对证据时填 []。
4. 不要因列表看起来不够丰富而补写。每项都必须在提供的原文片段中找到直接依据。
"""

V5_KEYWORD_EVIDENCE_RULES = """
V5 取证规则：用户文本带有“条件数值证据”和“结果指标证据”标签。这两段由全文中
的关键词和数值单位定位，不依赖 PDF 的章节标题。
1. experimental_conditions 优先且仅依据“条件数值证据”，只保留本论文的调制格式、
   波特率/比特率、距离和链路、频率/波长、接收或输入功率、采样率、明确算法参数。
   忽略参考文献编号、公式编号、一般器件介绍和没有实验语境的背景数字。
2. main_results 优先且仅依据“结果指标证据”，只保留 BER、FEC 阈值、功率罚、
   灵敏度、增益、可达距离等带数值或明确比较对象的结论；每条保留条件。
3. method_name 仅可依据“论文开头”或“方法命名证据”中作者明确命名的短语；若只是
   普通技术描述则填 null。标签是来源提示，绝不写入输出字段。
4. 不能由一条可直接核对的原文支持的内容不要输出；条件或结果不存在时填 []。
"""

RESULT_REFINEMENT_PROMPT = """你只负责论文的 main_results 字段精修。
请只依据用户提供的“结果指标证据”原文，不得使用外部知识、摘要推测或常识补全。
你必须只返回一个合法 JSON 对象，严格为：
{"main_results": ["指标: 数值 | condition: 条件", ...]}

规则：
1. 每项只写一个可核对的结果；必须含数值、阈值或明确比较对象，并尽量保留适用条件。
2. 优先 BER、FEC 阈值、功率罚、接收灵敏度、增益、传输距离、迭代收益。
3. 不写实验条件本身；不写没有数值或明确比较对象的笼统结论；没有可靠结果时返回空数组 []。
4. 不要返回 title、authors 或任何其他字段，不要解释。
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
        "modulation: 16QAM",
        "baud_rate: 16 Gbaud",
        "fiber_length: 20 km",
        "fiber_type: standard single-mode fiber",
        "wavelength: 1550 nm",
        "received_optical_power: -18 dBm",
    ],
    "main_results": [
        "BER: 2.1e-3 | condition: received_optical_power -18 dBm",
        "BER: below 7% HD-FEC threshold | condition: received_optical_power -18 dBm",
    ],
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


def build_evidence_extraction_messages(evidence_text: str) -> list[dict[str, str]]:
    """为 V4 组装“带来源标签的证据片段 → 11 字段 JSON”消息。"""

    cleaned_text = evidence_text.strip()
    if not cleaned_text:
        raise ValueError("evidence_text 不能为空")
    schema = json.dumps(PaperRecord.model_json_schema(), ensure_ascii=False, indent=2)
    example_json = json.dumps(FEW_SHOT_RESULT, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema) + V4_EVIDENCE_RULES},
        {"role": "user", "content": f"示例论文文本：\n{FEW_SHOT_TEXT}"},
        {"role": "assistant", "content": example_json},
        {"role": "user", "content": f"请只根据下面带标签的原文证据抽取 JSON：\n\n{cleaned_text}"},
    ]


def build_keyword_evidence_extraction_messages(evidence_text: str) -> list[dict[str, str]]:
    """为 V5 组装关键词证据片段与字段范围约束。"""

    cleaned_text = evidence_text.strip()
    if not cleaned_text:
        raise ValueError("evidence_text 不能为空")
    schema = json.dumps(PaperRecord.model_json_schema(), ensure_ascii=False, indent=2)
    example_json = json.dumps(FEW_SHOT_RESULT, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema) + V5_KEYWORD_EVIDENCE_RULES},
        {"role": "user", "content": f"示例论文文本：\n{FEW_SHOT_TEXT}"},
        {"role": "assistant", "content": example_json},
        {"role": "user", "content": f"请只根据下面带标签的原文证据抽取 JSON：\n\n{cleaned_text}"},
    ]


def build_result_refinement_messages(result_evidence_text: str) -> list[dict[str, str]]:
    """为 V6 组装只返回 ``main_results`` 的专用消息。"""

    cleaned_text = result_evidence_text.strip()
    if not cleaned_text:
        raise ValueError("result_evidence_text 不能为空")
    example = json.dumps(
        {"main_results": FEW_SHOT_RESULT["main_results"]},
        ensure_ascii=False,
        indent=2,
    )
    return [
        {"role": "system", "content": RESULT_REFINEMENT_PROMPT},
        {
            "role": "user",
            "content": "示例结果证据：\nBER is 2.1e-3 at -18 dBm, below 7% HD-FEC.",
        },
        {"role": "assistant", "content": example},
        {
            "role": "user",
            "content": f"请从下面结果证据中只抽取 main_results：\n\n{cleaned_text}",
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
