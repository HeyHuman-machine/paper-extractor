"""M2 Prompt 契约测试。"""

import json

import pytest

from app.models import PaperRecord
from app.prompts import FEW_SHOT_RESULT, build_extraction_messages


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
    assert json.loads(messages[2]["content"]) == FEW_SHOT_RESULT
    PaperRecord.model_validate(FEW_SHOT_RESULT)


def test_prompt_rejects_blank_paper_text() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        build_extraction_messages("   ")
