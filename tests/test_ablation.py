import json

from app.models import PaperRecord
from eval.ablation import _add_posthoc_measurements, _markdown, _summarize


def test_posthoc_validation_does_not_change_raw_record():
    raw = PaperRecord(
        title="Paper",
        authors=["A"],
        doc_type="journal_article",
        problem="Problem",
        summary="Summary",
    ).model_dump(mode="json")
    item = {"raw_record": raw.copy()}

    _add_posthoc_measurements(item)

    assert item["posthoc_schema_valid"] is True
    assert item["raw_record"] == raw
    assert item["field_completeness"] > 0


def test_summary_counts_transport_and_content_retries_separately():
    records = [
        {
            "flow_success": True,
            "posthoc_schema_valid": True,
            "field_completeness": 1.0,
            "attempts": [
                {"tokens": 10, "transport_retry_count": 1},
                {"tokens": 20, "transport_retry_count": 0},
            ],
            "duration_ms": 1000,
            "failure_stage": None,
        },
        {
            "flow_success": False,
            "posthoc_schema_valid": False,
            "field_completeness": 0.0,
            "attempts": [],
            "duration_ms": 2000,
            "failure_stage": "json_parse",
        },
    ]

    summary = _summarize(records, elapsed_ms=3000)

    assert summary["flow_success_count"] == 1
    assert summary["posthoc_schema_valid_count"] == 1
    assert summary["average_content_repair_retries"] == 0.5
    assert summary["average_transport_retries_per_paper"] == 0.5
    assert summary["total_tokens"] == 30
    assert summary["failure_stages"] == {"json_parse": 1}
