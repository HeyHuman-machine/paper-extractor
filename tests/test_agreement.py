"""A1 标注一致性计算测试。"""

import json

from app.models import DocumentType, PaperRecord
from eval.agreement import compute_agreement


def _record() -> dict:
    return PaperRecord(
        title="Paper",
        authors=["A"],
        year=2024,
        venue="Venue",
        doc_type=DocumentType.JOURNAL_ARTICLE,
        problem="Problem",
        method_name="Named Method",
        experimental_conditions=["baud_rate: 16 Gbaud", "fiber_length: 20 km"],
        main_results=["BER: 1e-3 | condition: 20 km"],
        limitations=None,
        summary="Summary",
    ).model_dump(mode="json")


def test_agreement_uses_same_low_field_rules(tmp_path) -> None:
    truth = tmp_path / "truth"
    recheck = tmp_path / "recheck"
    truth.mkdir()
    recheck.mkdir()
    (truth / "paper.json").write_text(
        json.dumps({"filename": "paper.pdf", "needs_review": False, "record": _record()}),
        encoding="utf-8",
    )
    (recheck / "paper.json").write_text(
        json.dumps(
            {
                "filename": "paper.pdf",
                "needs_review": False,
                "review": {
                    "method_name": "Named Method",
                    "experimental_conditions": ["fiber_length: 20 km", "baud_rate: 16 Gbaud"],
                    "main_results": ["BER: 1e-3 | condition: 20 km"],
                },
            }
        ),
        encoding="utf-8",
    )
    (recheck / "_template.json").write_text(
        json.dumps({"filename": "example.pdf", "needs_review": True, "review": {}}),
        encoding="utf-8",
    )

    report = compute_agreement(truth, recheck)

    assert report["sample_count"] == 1
    assert report["fields"]["method_name"]["score"] == 1.0
    assert report["fields"]["experimental_conditions"]["f1"] == 1.0
    assert report["fields"]["main_results"]["f1"] == 1.0
    assert report["invalid_rechecks"] == []
