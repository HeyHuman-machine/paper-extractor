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
        "datasets": [],
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

