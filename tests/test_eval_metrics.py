"""M9 字段指标测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import DocumentType, PaperRecord
from eval.metrics import (
    atomic_fact_precision_recall_f1,
    evaluate_records,
    fuzzy_match,
    load_ground_truth,
    normalize_text,
    semantic_list_precision_recall_f1,
    set_precision_recall_f1,
)


def record(**changes: object) -> PaperRecord:
    data = {
        "title": "Optical-Fiber Method",
        "authors": ["Alice Zhang", "Bob Li"],
        "year": 2025,
        "venue": "IEEE JLT",
        "doc_type": DocumentType.JOURNAL_ARTICLE,
        "problem": "降低光通信系统误码率",
        "method_name": "Method-X",
        "experimental_conditions": ["20 km SSMF", "16 QAM"],
        "main_results": ["BER: 1e-5"],
        "limitations": None,
        "summary": "一篇用于评测的光通信论文。",
    }
    return PaperRecord.model_validate({**data, **changes})


def test_normalize_and_fuzzy_match_ignore_case_punctuation_and_spaces() -> None:
    assert normalize_text(" IEEE JLT-2025 ") == "ieeejlt2025"
    assert fuzzy_match("Optical-Fiber Method", "optical fiber method") is True
    assert fuzzy_match("Method A", "Completely Different") is False


def test_set_metric_returns_precision_recall_and_f1() -> None:
    precision, recall, f1 = set_precision_recall_f1(
        ["Alice Zhang", "Bob Li"],
        ["alice-zhang", "Carol"],
    )
    assert precision == pytest.approx(0.5)
    assert recall == pytest.approx(0.5)
    assert f1 == pytest.approx(0.5)
    assert set_precision_recall_f1([], []) == (1.0, 1.0, 1.0)


def test_semantic_list_metric_accepts_scientific_notation_and_format_variants() -> None:
    precision, recall, f1 = semantic_list_precision_recall_f1(
        ["BER: 2.1×10^-3 | condition: received optical power -18 dBm"],
        ["BER: 2.1e-3 | condition: received_optical_power -18 dBm"],
        threshold=0.62,
    )

    assert (precision, recall, f1) == (1.0, 1.0, 1.0)


def test_semantic_list_metric_rejects_conflicting_numbers() -> None:
    assert semantic_list_precision_recall_f1(
        ["fiber_length: 20 km"],
        ["fiber_length: 50 km"],
        threshold=0.56,
    ) == (0.0, 0.0, 0.0)


def test_atomic_fact_metric_matches_split_and_merged_conditions() -> None:
    precision, recall, f1 = atomic_fact_precision_recall_f1(
        ["Baud rates: 2 Gbaud and 4 Gbaud; SSMF distances: 1 km and 5 km"],
        [
            "baud_rate: 2 Gbaud",
            "baud_rate: 4 Gbaud",
            "fiber_length: 1 km",
            "fiber_length: 5 km",
            "fiber_type: SSMF",
        ],
    )

    assert (precision, recall, f1) == (1.0, 1.0, 1.0)


def test_atomic_fact_metric_rejects_wrong_measurement_value() -> None:
    precision, recall, f1 = atomic_fact_precision_recall_f1(
        ["BER: below 3.8e-3 HD-FEC | condition: 10 km SSMF"],
        ["BER: below 1.0e-2 HD-FEC | condition: 50 km SSMF"],
    )

    assert precision == pytest.approx(0.6)
    assert recall == pytest.approx(0.6)
    assert f1 == pytest.approx(0.6)


def test_evaluation_uses_eight_objective_fields_and_penalizes_missing_paper() -> None:
    truth = {"a.pdf": record(), "b.pdf": record(title="Second Paper")}
    prediction = {
        "a.pdf": {
            **record().model_dump(mode="json"),
            "title": "optical fiber method",
        }
    }

    result = evaluate_records(truth, prediction)

    assert result["prediction_success_count"] == 1
    assert result["extraction_success_rate"] == 0.5
    assert len(result["fields"]) == 8
    assert result["fields"]["title"]["accuracy"] == 0.5
    assert result["fields"]["authors"]["f1"] == 0.5
    assert result["manual_fields"]["summary"]["score"] is None


def test_ground_truth_only_accepts_human_confirmed_valid_records(tmp_path: Path) -> None:
    pending = {
        "filename": "pending.pdf",
        "needs_review": True,
        "record": {},
    }
    confirmed = {
        "filename": "paper.pdf",
        "needs_review": False,
        "record": record().model_dump(mode="json"),
    }
    (tmp_path / "pending.json").write_text(json.dumps(pending), encoding="utf-8")
    (tmp_path / "confirmed.json").write_text(
        json.dumps(confirmed, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    (tmp_path / "_template.json").write_text("{}", encoding="utf-8")

    labels = load_ground_truth(tmp_path)

    assert list(labels.records) == ["paper.pdf"]
    assert labels.pending_files == ["pending.pdf"]
    assert labels.invalid_files == ["broken.json"]


def test_duplicate_confirmed_filename_is_reported_invalid(tmp_path: Path) -> None:
    payload = {
        "filename": "paper.pdf",
        "needs_review": False,
        "record": record().model_dump(mode="json"),
    }
    (tmp_path / "one.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "two.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    labels = load_ground_truth(tmp_path)

    assert len(labels.records) == 1
    assert labels.invalid_files == ["two.json（文件名重复）"]
