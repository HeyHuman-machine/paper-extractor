"""M9 字段指标：按字段语义选择不同的比较方法。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from app.models import PaperRecord


EXACT_FIELDS = ("year", "doc_type")
FUZZY_FIELDS = ("title", "method_name", "venue")
SET_FIELDS = ("authors", "experimental_conditions", "main_results")
MANUAL_FIELDS = ("problem", "limitations", "summary")
AUTO_FIELDS = EXACT_FIELDS + FUZZY_FIELDS + SET_FIELDS
FIELD_LABELS = {
    "title": "标题",
    "authors": "作者",
    "year": "年份",
    "venue": "期刊 / 会议",
    "doc_type": "文档类型",
    "problem": "研究问题",
    "method_name": "方法名称",
    "experimental_conditions": "实验条件",
    "main_results": "主要结果",
    "limitations": "局限性",
    "summary": "摘要总结",
}


@dataclass(frozen=True, slots=True)
class GroundTruthSet:
    """人工标注目录的读取结果。"""

    records: dict[str, PaperRecord]
    pending_files: list[str]
    invalid_files: list[str]


def normalize_text(value: Any) -> str:
    """转小写并移除标点、空格，减少格式差异造成的误判。"""

    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def fuzzy_match(expected: Any, actual: Any, threshold: float = 0.9) -> bool:
    """归一化后计算字符相似度，默认达到 0.9 视为正确。"""

    expected_text = normalize_text(expected)
    actual_text = normalize_text(actual)
    if not expected_text or not actual_text:
        return expected_text == actual_text
    return SequenceMatcher(None, expected_text, actual_text).ratio() >= threshold


_METHOD_SUFFIX_PATTERN = re.compile(
    r"(?:algorithm|scheme|method|architecture|receiver|transceiver|"
    r"processing|算法|方案|方法|架构|接收机|收发机|处理)\\s*$",
    re.IGNORECASE,
)
_METHOD_PARENTHETICAL_PATTERN = re.compile(r"[（(]([^()（）]*)[)）]")
_METHOD_COMPARISON_PATTERN = re.compile(
    r"\\s*(?:versus|vs\\.?|compared\\s+with|comparison\\s+with|对比|比较)\\s+.*$",
    re.IGNORECASE,
)
_METHOD_ACRONYM_PATTERN = re.compile(r"(?<![A-Za-z])[A-Z][A-Z0-9]{1,9}(?![A-Za-z0-9])")
_METHOD_STOP_WORDS = frozenset({"a", "an", "and", "based", "by", "for", "of", "on", "the", "with"})


def calibrated_method_match(expected: Any, actual: Any) -> bool:
    """B1 候选规则：比较方法名称的主方法，而非括号内解释或通用后缀。"""

    matched, _ = calibrated_method_match_detail(expected, actual)
    return matched


def calibrated_method_match_detail(expected: Any, actual: Any) -> tuple[bool, str]:
    """返回 B1 方法名称判定及命中的确定性规则名称。

    该函数只用于 B1 的平行评分，不替换既有 ``fuzzy_match`` 默认规则。规则
    仅处理可复核的表述差异：空值、括号说明、比较对象、通用后缀和显式缩写。
    不做中英文语义翻译，也不把遗漏关键组件的短答案判为正确。
    """

    baseline = fuzzy_match(expected, actual)
    if baseline:
        return True, "baseline_fuzzy_0.90"

    expected_text = str(expected or "").strip()
    actual_text = str(actual or "").strip()
    if not expected_text or not actual_text:
        return False, "empty_value_mismatch"

    expected_forms = _method_core_forms(expected_text)
    actual_forms = _method_core_forms(actual_text)
    if expected_forms & actual_forms:
        return True, "core_normalization"

    if _has_explicit_acronym_expansion(expected_text, actual_text):
        return True, "explicit_acronym_expansion"

    for expected_form in expected_forms:
        for actual_form in actual_forms:
            if not expected_form or not actual_form:
                continue
            similarity = SequenceMatcher(None, expected_form, actual_form).ratio()
            if similarity >= 0.75:
                return True, "normalized_fuzzy_0.75"

    return False, "no_safe_equivalence"


def _method_core_forms(value: str) -> set[str]:
    """生成仅删除可解释修饰语的方法名称候选形式。"""

    normalized = unicodedata.normalize("NFKC", value)
    without_parentheses = _METHOD_PARENTHETICAL_PATTERN.sub(
        _drop_explanatory_parenthetical,
        normalized,
    )
    without_comparison = _METHOD_COMPARISON_PATTERN.sub("", without_parentheses)
    forms = {normalized, without_parentheses, without_comparison}
    forms.update(_METHOD_SUFFIX_PATTERN.sub("", item).strip() for item in tuple(forms))
    return {normalize_text(item) for item in forms if normalize_text(item)}


def _drop_explanatory_parenthetical(match: re.Match[str]) -> str:
    """只移除解释性括号；含“组合/共同使用”信号的复合方法仍保留。"""

    content = match.group(1).casefold()
    composite_signals = ("together with", "combined with", "in combination with")
    return match.group(0) if any(signal in content for signal in composite_signals) else " "


def _has_explicit_acronym_expansion(expected: str, actual: str) -> bool:
    """仅在“纯缩写 ↔ 其全称”时放行，避免把复合方法中的一个部件当作全方法。"""

    for acronym_source, expansion_source in ((expected, actual), (actual, expected)):
        for acronym in _METHOD_ACRONYM_PATTERN.findall(acronym_source):
            acronym_form = normalize_text(_METHOD_SUFFIX_PATTERN.sub("", acronym_source)).upper()
            if acronym_form != acronym or len(acronym) < 2:
                continue
            initials = "".join(
                token[0].upper()
                for token in re.findall(r"[A-Za-z]+", expansion_source)
                if token.casefold() not in _METHOD_STOP_WORDS
            )
            if initials == acronym:
                return True
    return False


def set_precision_recall_f1(
    expected: list[str] | None,
    actual: list[str] | None,
) -> tuple[float, float, float]:
    """把列表归一化为集合，返回 precision、recall、F1。"""

    expected_set = {normalize_text(item) for item in expected or [] if normalize_text(item)}
    actual_set = {normalize_text(item) for item in actual or [] if normalize_text(item)}
    if not expected_set and not actual_set:
        return 1.0, 1.0, 1.0
    true_positive = len(expected_set & actual_set)
    precision = true_positive / len(actual_set) if actual_set else 0.0
    recall = true_positive / len(expected_set) if expected_set else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


def semantic_list_precision_recall_f1(
    expected: list[str] | None,
    actual: list[str] | None,
    *,
    threshold: float,
) -> tuple[float, float, float]:
    """用确定性的一对一文本相似匹配比较事实列表。

    实验条件和主要结果在不改变事实的前提下，常会出现连字符、科学计数法、
    单位空格、拆分方式等写法差异。此函数不调用 LLM，而是使用归一化后的
    字符串相似度做最大匹配，仍然会惩罚漏项、多项和明显不相关的文本。
    """

    expected_items = [item for item in expected or [] if normalize_text(item)]
    actual_items = [item for item in actual or [] if normalize_text(item)]
    if not expected_items and not actual_items:
        return 1.0, 1.0, 1.0

    candidates: list[tuple[float, int, int]] = []
    for expected_index, expected_item in enumerate(expected_items):
        for actual_index, actual_item in enumerate(actual_items):
            score = _fact_similarity(expected_item, actual_item)
            if score >= threshold:
                candidates.append((score, expected_index, actual_index))

    matched_expected: set[int] = set()
    matched_actual: set[int] = set()
    matches = 0
    for _, expected_index, actual_index in sorted(candidates, reverse=True):
        if expected_index in matched_expected or actual_index in matched_actual:
            continue
        matched_expected.add(expected_index)
        matched_actual.add(actual_index)
        matches += 1

    precision = matches / len(actual_items) if actual_items else 0.0
    recall = matches / len(expected_items) if expected_items else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


_UNIT_FACT_PATTERN = re.compile(
    r"(?<![a-z0-9])-?\d+(?:\.\d+)?(?:e[+-]?\d+)?\s*"
    r"(?:tbaud|gbaud|mbaud|khz|mhz|ghz|thz|nm|km|m|dbm|db|%|ps|ns|us|ms|s)",
    re.IGNORECASE,
)
_CATEGORY_FACT_PATTERN = re.compile(
    r"\b(?:\d+)?(?:qpsk|psk|qam|pam\d*|bpsk|ofdm|ssmf|hdfec|fec|btb|"
    r"singleendedpd|iqmodulator|mzm|ecl)\b",
    re.IGNORECASE,
)
_METRIC_FACT_PATTERN = re.compile(
    r"\b(?:ber|qfactor|osnr|evm|spectralefficiency)\b",
    re.IGNORECASE,
)
_SCIENTIFIC_VALUE_PATTERN = re.compile(
    r"(?<![a-z0-9])\d+(?:\.\d+)?e[+-]?\d+(?![a-z0-9])",
    re.IGNORECASE,
)


def atomic_fact_precision_recall_f1(
    expected: list[str] | None,
    actual: list[str] | None,
) -> tuple[float, float, float]:
    """把列表文本拆成可复核事实后计算集合 F1。

    人工标注可能把“2 Gbaud、4 Gbaud、1 km、5 km”写在同一句，V2 Prompt
    则将它们拆成四条。评测目标应是事实是否出现，而不是两边是否恰好采用同一
    分句方式。因此这里提取数值+单位、调制格式、关键器件和结果指标后再比较。
    """

    expected_facts = _atomic_facts(expected)
    actual_facts = _atomic_facts(actual)
    if not expected_facts and not actual_facts:
        return 1.0, 1.0, 1.0
    true_positive = len(expected_facts & actual_facts)
    precision = true_positive / len(actual_facts) if actual_facts else 0.0
    recall = true_positive / len(expected_facts) if expected_facts else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


def _atomic_facts(items: list[str] | None) -> set[str]:
    """从列表中提取不依赖措辞的事实 token。"""

    facts: set[str] = set()
    for item in items or []:
        normalized = _normalize_scientific_notation(item).casefold()
        facts.update(
            normalize_text(match.group(0))
            for match in _UNIT_FACT_PATTERN.finditer(normalized)
        )
        facts.update(
            normalize_text(match.group(0))
            for match in _SCIENTIFIC_VALUE_PATTERN.finditer(normalized)
        )
        facts.update(match.group(0) for match in _CATEGORY_FACT_PATTERN.finditer(normalized))
        facts.update(match.group(0) for match in _METRIC_FACT_PATTERN.finditer(normalized))
    return facts


def _fact_similarity(expected: str, actual: str) -> float:
    """比较单条可核对事实；数值冲突时不把相似措辞误判为匹配。"""

    expected_text = normalize_text(_normalize_scientific_notation(expected))
    actual_text = normalize_text(_normalize_scientific_notation(actual))
    if not expected_text or not actual_text:
        return 0.0

    expected_numbers = set(re.findall(r"\d+(?:\.\d+)?(?:e[+-]?\d+)?", expected_text))
    actual_numbers = set(re.findall(r"\d+(?:\.\d+)?(?:e[+-]?\d+)?", actual_text))
    if expected_numbers and actual_numbers and not (expected_numbers & actual_numbers):
        return 0.0
    return SequenceMatcher(None, expected_text, actual_text).ratio()


def _normalize_scientific_notation(value: str) -> str:
    """把 ``2.1×10^-3``、``2.1 x 10−3`` 统一为 ``2.1e-3``。"""

    normalized = unicodedata.normalize("NFKC", value).replace("−", "-")
    return re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:×|x|\*)\s*10\s*\^?\s*([+-]?\d+)",
        r"\1e\2",
        normalized,
        flags=re.IGNORECASE,
    )


def load_ground_truth(directory: Path | str) -> GroundTruthSet:
    """读取已确认标注；`needs_review=true` 的草稿不会进入评分。"""

    root = Path(directory)
    records: dict[str, PaperRecord] = {}
    pending: list[str] = []
    invalid: list[str] = []
    if not root.exists():
        return GroundTruthSet(records, pending, invalid)

    for path in sorted(root.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            filename = str(payload["filename"]).strip()
            if payload.get("needs_review", True):
                pending.append(filename or path.name)
                continue
            record = PaperRecord.model_validate(payload["record"])
            key = _filename_key(filename)
            if key in records:
                invalid.append(f"{path.name}（文件名重复）")
                continue
            records[key] = record
        except (OSError, ValueError, KeyError, TypeError):
            invalid.append(path.name)
    return GroundTruthSet(records, pending, invalid)


def load_predictions(path: Path | str) -> dict[str, dict[str, Any]]:
    """读取 M6 导出的 JSON，并按文件名建立成功结果索引。"""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    results = payload.get("results", []) if isinstance(payload, dict) else payload
    if not isinstance(results, list):
        raise ValueError("预测文件必须包含 results 数组")
    indexed: dict[str, dict[str, Any]] = {}
    for item in results:
        if isinstance(item, dict) and item.get("filename"):
            indexed[_filename_key(str(item["filename"]))] = item
    return indexed


def evaluate_records(
    ground_truth: dict[str, PaperRecord],
    predictions: dict[str, dict[str, Any]],
    *,
    method_name_matcher: Callable[[Any, Any], bool] = fuzzy_match,
) -> dict[str, Any]:
    """评估一轮预测；缺失或失败论文在自动字段上计 0 分。"""

    total = len(ground_truth)
    if total == 0:
        raise ValueError("没有已确认的人工标注，不能计算准确率")

    fields: dict[str, dict[str, Any]] = {}
    for field in EXACT_FIELDS:
        correct = sum(
            name in predictions
            and _exact_value(getattr(truth, field), predictions[name].get(field))
            for name, truth in ground_truth.items()
        )
        fields[field] = _accuracy_metric("exact", correct, total)

    for field in FUZZY_FIELDS:
        matcher = method_name_matcher if field == "method_name" else fuzzy_match
        correct = sum(
            matcher(getattr(truth, field), predictions.get(name, {}).get(field))
            for name, truth in ground_truth.items()
            if name in predictions
        )
        fields[field] = _accuracy_metric("fuzzy", correct, total)

    for field in SET_FIELDS:
        scores = []
        for name, truth in ground_truth.items():
            if name not in predictions:
                scores.append((0.0, 0.0, 0.0))
            else:
                expected = getattr(truth, field)
                actual = predictions[name].get(field)
                if field in {"experimental_conditions", "main_results"}:
                    scores.append(atomic_fact_precision_recall_f1(expected, actual))
                else:
                    scores.append(set_precision_recall_f1(expected, actual))
        precision = sum(score[0] for score in scores) / total
        recall = sum(score[1] for score in scores) / total
        f1 = sum(score[2] for score in scores) / total
        fields[field] = {
            "kind": (
                "atomic_fact_set"
                if field in {"experimental_conditions", "main_results"}
                else "set"
            ),
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "score": f1,
            "total": total,
        }

    success_count = sum(name in predictions for name in ground_truth)
    overall = sum(fields[field]["score"] for field in AUTO_FIELDS) / len(AUTO_FIELDS)
    return {
        "ground_truth_count": total,
        "prediction_success_count": success_count,
        "prediction_missing_count": total - success_count,
        "extraction_success_rate": success_count / total,
        "overall_auto_score": overall,
        "fields": fields,
        "manual_fields": {
            field: {
                "kind": "manual_required",
                "score": None,
                "reason": "自由文本不存在唯一标准答案，不进行不可靠的自动评分",
            }
            for field in MANUAL_FIELDS
        },
    }


def _accuracy_metric(kind: str, correct: int, total: int) -> dict[str, Any]:
    return {
        "kind": kind,
        "correct": correct,
        "total": total,
        "accuracy": correct / total,
        "score": correct / total,
    }


def _exact_value(expected: Any, actual: Any) -> bool:
    expected_value = getattr(expected, "value", expected)
    actual_value = getattr(actual, "value", actual)
    return expected_value == actual_value


def safe_label_filename(filename: str) -> str:
    """把论文文件名转换为可读且适合 Windows 的标注文件名。"""

    stem = Path(filename).stem.strip() or "paper"
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem)
    return f"{safe[:80]}.json"


def _filename_key(filename: str) -> str:
    return Path(filename).name.casefold()
