"""M2 Prompt 契约测试。"""

import json

import pytest

from app.models import PaperRecord
from app.prompts import (
    FEW_SHOT_RESULT,
    append_repair_message,
    build_extraction_messages,
)


def test_prompt_contains_json_schema_and_few_shot() -> None:
    messages = build_extraction_messages("A new paper about robust extraction.")

    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "JSON Schema" in messages[0]["content"]
    assert '"title"' in messages[0]["content"]
    assert "禁止使用外部知识" in messages[0]["content"]
    assert "experimental_conditions" in messages[0]["content"]
    assert "不得根据实验条件自行推断" in messages[0]["content"]
    assert "不得写“未明确给出”" in messages[0]["content"]
    assert "必须直接填 null" in messages[0]["content"]
    assert "datasets" not in messages[0]["content"]
    assert json.loads(messages[2]["content"]) == FEW_SHOT_RESULT
    PaperRecord.model_validate(FEW_SHOT_RESULT)


def test_prompt_rejects_blank_paper_text() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        build_extraction_messages("   ")


def test_repair_message_keeps_original_messages_unchanged() -> None:
    original = build_extraction_messages("a fictional paper")

    repaired = append_repair_message(
        original,
        raw_output='{"year": 1949}',
        stage="schema_validate",
        error_message="year 必须大于等于 1950",
    )

    assert len(original) == 4
    assert len(repaired) == 6
    assert repaired[-2] == {"role": "assistant", "content": '{"year": 1949}'}
    assert "schema_validate" in repaired[-1]["content"]
    assert "year 必须大于等于 1950" in repaired[-1]["content"]
