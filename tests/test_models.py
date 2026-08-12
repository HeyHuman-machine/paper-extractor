"""共享 Pydantic Schema 的关键约束测试。"""

import pytest
from pydantic import ValidationError

from app.models import DocumentType, PaperRecord


def valid_record_data() -> dict[str, object]:
    """返回一份可以通过校验的最小论文数据。"""

    return {
        "title": "A Practical Paper",
        "authors": ["Stella", "Alice"],
        "year": 2026,
        "venue": "Optics Express",
        "doc_type": "journal_article",
        "problem": "降低单光电探测器接收系统中的信号拍频干扰。",
        "method_name": "Example Method",
        "experimental_conditions": ["16-Gbaud 16QAM", "20 km SSMF"],
        "main_results": ["BER: 1e-5 @ 10 dB SNR"],
        "limitations": None,
        "summary": "本文提出一种低复杂度方案，并通过仿真验证其有效性。",
    }


def test_valid_paper_record() -> None:
    """合法的11字段数据应通过校验并转换枚举。"""

    record = PaperRecord.model_validate(valid_record_data())

    assert record.doc_type is DocumentType.JOURNAL_ARTICLE
    assert record.authors == ["Stella", "Alice"]


@pytest.mark.parametrize("year", [1949, 2031])
def test_year_must_be_in_supported_range(year: int) -> None:
    """年份必须在1950到2030之间。"""

    data = valid_record_data()
    data["year"] = year

    with pytest.raises(ValidationError):
        PaperRecord.model_validate(data)


def test_required_text_cannot_be_blank() -> None:
    """标题经过空白清理后不能是空字符串。"""

    data = valid_record_data()
    data["title"] = "   "

    with pytest.raises(ValidationError):
        PaperRecord.model_validate(data)


def test_authors_need_at_least_one_real_name() -> None:
    """作者列表不能用空字符串蒙混过关。"""

    data = valid_record_data()
    data["authors"] = ["  "]

    with pytest.raises(ValidationError):
        PaperRecord.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "length"),
    [("problem", 201), ("summary", 401)],
)
def test_long_text_fields_have_limits(field_name: str, length: int) -> None:
    """problem 和 summary 超过规格长度时必须失败。"""

    data = valid_record_data()
    data[field_name] = "测" * length

    with pytest.raises(ValidationError):
        PaperRecord.model_validate(data)


def test_document_type_must_be_known_enum_value() -> None:
    """未知文档类型不能进入系统。"""

    data = valid_record_data()
    data["doc_type"] = "blog_post"

    with pytest.raises(ValidationError):
        PaperRecord.model_validate(data)


@pytest.mark.parametrize(
    "limitation",
    [
        "未明确提及，但可能受限于输入光功率。",
        "该方案或许存在复杂度问题。",
        "The method may be limited by received power.",
        "作者未明确陈述局限性。",
    ],
)
def test_limitations_reject_model_inference(limitation: str) -> None:
    data = valid_record_data()
    data["limitations"] = limitation

    with pytest.raises(ValidationError, match="不能使用推测性措辞"):
        PaperRecord.model_validate(data)


def test_explicit_author_limitation_is_allowed() -> None:
    data = valid_record_data()
    data["limitations"] = "作者指出当前实验仅验证单偏振，未来将评估偏振复用。"

    record = PaperRecord.model_validate(data)

    assert record.limitations is not None


@pytest.mark.parametrize(
    "condition",
    [
        "波特率：未明确给出具体数值",
        "波长：根据参考文献推断，但正文未明确",
        "Transmission distance: not specified",
    ],
)
def test_experimental_conditions_reject_missing_or_inferred_items(
    condition: str,
) -> None:
    data = valid_record_data()
    data["experimental_conditions"] = [condition]

    with pytest.raises(ValidationError, match="只能包含原文明确给出的实验条件"):
        PaperRecord.model_validate(data)
