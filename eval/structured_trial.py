"""B2 结构化字段试点：独立于 M1-M8 主流程的模型、模板与评分规则。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from eval.metrics import normalize_text


class ConditionItem(BaseModel):
    """一个可评测的实验条件：名称、数值/取值和可选单位。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    unit: str | None = None


class ResultItem(BaseModel):
    """一个可评测的主要结果：指标、数值、单位和可选适用条件。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    metric: str = Field(min_length=1)
    value: str = Field(min_length=1)
    unit: str | None = None
    condition: str | None = None


class StructuredFieldRecord(BaseModel):
    """B2 试点仅覆盖两个低分列表字段，不替换主项目的 ``PaperRecord``。"""

    model_config = ConfigDict(extra="forbid")

    experimental_conditions: list[ConditionItem] = Field(default_factory=list)
    main_results: list[ResultItem] = Field(default_factory=list)


STRUCTURED_TRIAL_PROMPT = """你是严谨的光通信论文信息抽取助手。
只依据用户提供的论文文本，不得使用外部知识补全或猜测。只返回一个合法 JSON 对象，
格式必须符合 Schema。此任务只抽取两个字段：

1. experimental_conditions：每个对象只表示一个明确条件，name 用英文标准名，value
   只写数值或明确取值，unit 单独填写；例如 {"name":"fiber_length","value":"80","unit":"km"}。
2. main_results：每个对象只表示一个可核对结果，metric 用英文标准指标名，value 和 unit
   分开填写，condition 仅填写适用条件；例如 {"metric":"BER","value":"2.1e-3","unit":null,
   "condition":"80 km SSMF"}。

规则：不得把多个独立事实合并为一项；必须保留数值和单位；没有直接证据时返回空列表；
不输出解释、Markdown 或其他字段。"""

STRUCTURED_FEW_SHOT = {
    "experimental_conditions": [
        {"name": "modulation", "value": "16QAM", "unit": None},
        {"name": "baud_rate", "value": "16", "unit": "Gbaud"},
        {"name": "fiber_length", "value": "20", "unit": "km"},
    ],
    "main_results": [
        {
            "metric": "BER",
            "value": "2.1e-3",
            "unit": None,
            "condition": "received optical power -18 dBm",
        }
    ],
}


_SYNONYM_GROUPS = {
    "ber": {"ber", "biterrorrate", "errorrate", "误码率"},
    "osnr": {"osnr", "opticalsignaltonoiseratio", "光信噪比"},
    "rop": {"rop", "receivedopticalpower", "receivedpower", "接收光功率"},
    "cspr": {"cspr", "carriertosignalpowerratio", "载波信号功率比"},
    "snr": {"snr", "signaltonoiseratio", "信噪比"},
    "baudrate": {"baudrate", "symbolrate", "波特率", "符号率"},
    "fiberlength": {"fiberlength", "transmissiondistance", "linklength", "光纤长度", "传输距离"},
}
_SYNONYM_INDEX = {term: canonical for canonical, terms in _SYNONYM_GROUPS.items() for term in terms}
_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class StructuredScore:
    """一个字段列表的 soft precision、recall、F1 与匹配贡献。"""

    precision: float
    recall: float
    f1: float
    matched_credit: float


def canonical_name(value: str) -> str:
    """归一化常见指标/条件同义词；未知项仍用可复核的普通归一化。"""

    normalized = normalize_text(value)
    return _SYNONYM_INDEX.get(normalized, normalized)


def structured_precision_recall_f1(
    expected: list[ConditionItem] | list[ResultItem],
    actual: list[ConditionItem] | list[ResultItem],
) -> StructuredScore:
    """用一对一最大 partial-credit 比对结构化列表。

    同名且数值（含单位）相符为 1.0；仅同名为 0.5。数值允许 5% 相对误差，
    条件只在两个结果都提供时要求完全归一化匹配。这样既不会因拆句扣光分，也
    不会把“同一个 BER 指标但数值错误”当成完全正确。
    """

    if not expected and not actual:
        return StructuredScore(1.0, 1.0, 1.0, 0.0)
    candidates: list[tuple[float, int, int]] = []
    for expected_index, expected_item in enumerate(expected):
        for actual_index, actual_item in enumerate(actual):
            credit = _item_credit(expected_item, actual_item)
            if credit:
                candidates.append((credit, expected_index, actual_index))

    used_expected: set[int] = set()
    used_actual: set[int] = set()
    total_credit = 0.0
    for credit, expected_index, actual_index in sorted(candidates, reverse=True):
        if expected_index in used_expected or actual_index in used_actual:
            continue
        used_expected.add(expected_index)
        used_actual.add(actual_index)
        total_credit += credit

    precision = total_credit / len(actual) if actual else 0.0
    recall = total_credit / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return StructuredScore(precision, recall, f1, total_credit)


def _item_credit(expected: ConditionItem | ResultItem, actual: ConditionItem | ResultItem) -> float:
    expected_name = canonical_name(_item_name(expected))
    actual_name = canonical_name(_item_name(actual))
    if expected_name != actual_name:
        return 0.0
    if isinstance(expected, ResultItem) and isinstance(actual, ResultItem):
        if expected.condition and actual.condition and normalize_text(expected.condition) != normalize_text(actual.condition):
            return 0.5
    return 1.0 if _same_measurement(expected.value, expected.unit, actual.value, actual.unit) else 0.5


def _item_name(item: ConditionItem | ResultItem) -> str:
    return item.name if isinstance(item, ConditionItem) else item.metric


def _same_measurement(expected_value: str, expected_unit: str | None, actual_value: str, actual_unit: str | None) -> bool:
    """比较数字和单位；无法可靠解析时保守地判为不相同。"""

    expected_number = _parse_number(expected_value)
    actual_number = _parse_number(actual_value)
    if expected_number is None or actual_number is None:
        return normalize_text(expected_value) == normalize_text(actual_value) and _same_unit(expected_unit, actual_unit)
    if not _same_unit(expected_unit, actual_unit):
        return False
    denominator = max(abs(expected_number), 1e-12)
    return abs(expected_number - actual_number) / denominator <= 0.05


def _parse_number(value: str) -> float | None:
    normalized = unicodedata.normalize("NFKC", value).replace("×10^", "e").replace("×10", "e")
    match = _NUMBER_PATTERN.search(normalized)
    return float(match.group(0)) if match else None


def _same_unit(expected: str | None, actual: str | None) -> bool:
    return normalize_text(expected) == normalize_text(actual)


def structured_template(filename: str) -> dict[str, Any]:
    """生成不含模型预测内容的 B2 人工标注模板。"""

    return {
        "filename": filename,
        "needs_review": True,
        "annotation_meta": {
            "split": "b2_structured_pilot",
            "review_status": "blank_pending_human_annotation",
            "reviewed_by": None,
            "reviewed_at": None,
            "note": "仅对照原论文填写；不得查看或复制本轮模型输出。数值与单位分开填写。",
        },
        "record": {
            "experimental_conditions": [],
            "main_results": [],
        },
        "evidence": {},
    }


def build_structured_trial_messages(paper_text: str) -> list[dict[str, str]]:
    """构建 B2 试点专用消息；不改变主流程的 11 字段 Prompt。"""

    cleaned_text = paper_text.strip()
    if not cleaned_text:
        raise ValueError("paper_text 不能为空")
    schema = json.dumps(StructuredFieldRecord.model_json_schema(), ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": STRUCTURED_TRIAL_PROMPT + "\n\nJSON Schema:\n" + schema},
        {"role": "user", "content": "示例论文文本：16-Gbaud 16QAM over 20 km fiber. BER is 2.1e-3 at -18 dBm."},
        {"role": "assistant", "content": json.dumps(STRUCTURED_FEW_SHOT, ensure_ascii=False)},
        {"role": "user", "content": f"请从下面论文文本中抽取结构化字段：\n\n{cleaned_text}"},
    ]


def append_structured_repair_message(
    messages: list[dict[str, str]], raw_output: str, error_message: str
) -> list[dict[str, str]]:
    """为 B2 结构化试点增加 JSON/Pydantic 修复回合。"""

    return [
        *messages,
        {"role": "assistant", "content": raw_output},
        {
            "role": "user",
            "content": "上次 JSON 不符合结构化 Schema：" + error_message[:1200]
            + "。请依据最初论文文本重新输出完整合法 JSON；不要解释。",
        },
    ]
