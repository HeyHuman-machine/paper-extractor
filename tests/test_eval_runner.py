"""M9 标注辅助、两轮报告与图片生成测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import DocumentType, PaperRecord
from eval.prepare_labels import prepare_blank_labels, prepare_labels
from eval.metrics import load_ground_truth, load_predictions
from eval.reporting import build_comparison
from eval.run_eval import run_evaluation


def record(title: str = "Paper A") -> dict:
    return PaperRecord(
        title=title,
        authors=["Alice"],
        year=2024,
        venue="Optics Express",
        doc_type=DocumentType.JOURNAL_ARTICLE,
        problem="验证评测流程",
        method_name="Method A",
        experimental_conditions=["20 km SSMF"],
        main_results=["BER: 1e-5"],
        limitations=None,
        summary="这是用于测试的论文摘要。",
    ).model_dump(mode="json")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_prepare_labels_creates_drafts_without_overwriting(tmp_path: Path) -> None:
    source = tmp_path / "m6.json"
    output = tmp_path / "labels"
    write_json(source, {"results": [{"filename": "论文.pdf", **record()}]})

    first = prepare_labels(source, output)
    first[0].write_text("KEEP", encoding="utf-8")
    second = prepare_labels(source, output)

    assert len(first) == 1
    assert second == []
    assert first[0].read_text(encoding="utf-8") == "KEEP"


def test_prepare_blank_labels_uses_only_document_names(tmp_path: Path) -> None:
    inputs = tmp_path / "papers"
    inputs.mkdir()
    (inputs / "blind-paper.pdf").write_bytes(b"not read by label preparation")
    (inputs / "ignore.txt").write_text("ignore", encoding="utf-8")

    created = prepare_blank_labels(inputs, tmp_path / "labels")
    payload = json.loads(created[0].read_text(encoding="utf-8"))

    assert len(created) == 1
    assert payload["filename"] == "blind-paper.pdf"
    assert payload["needs_review"] is True
    assert payload["record"]["title"] == ""
    assert payload["annotation_meta"]["split"] == "evaluation"


def test_run_eval_writes_markdown_json_and_real_png(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    baseline = tmp_path / "baseline.json"
    robust = tmp_path / "robust.json"
    output = tmp_path / "report"
    write_json(
        labels / "paper.json",
        {"filename": "paper.pdf", "needs_review": False, "record": record()},
    )
    wrong = {**record("Wrong Title"), "year": 2020}
    write_json(baseline, {"results": [{"filename": "paper.pdf", **wrong}]})
    write_json(robust, {"results": [{"filename": "paper.pdf", **record()}]})

    report, paths = run_evaluation(
        labels, baseline, robust, output, minimum_labels=30, allow_partial=True
    )

    assert report["is_partial"] is True
    assert report["overall_delta"] > 0
    assert paths["json"].exists()
    assert "自由文本" in paths["markdown"].read_text(encoding="utf-8")
    assert paths["chart"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_formal_report_requires_thirty_confirmed_labels(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    write_json(
        labels / "paper.json",
        {"filename": "paper.pdf", "needs_review": False, "record": record()},
    )
    prediction = tmp_path / "prediction.json"
    write_json(prediction, {"results": [{"filename": "paper.pdf", **record()}]})

    with pytest.raises(ValueError, match="至少需要 30 篇"):
        run_evaluation(labels, prediction, prediction, tmp_path / "report")


def test_comparison_report_keeps_custom_version_labels(tmp_path: Path) -> None:
    labels_dir = tmp_path / "labels"
    prediction = tmp_path / "prediction.json"
    write_json(
        labels_dir / "paper.json",
        {"filename": "paper.pdf", "needs_review": False, "record": record()},
    )
    write_json(prediction, {"results": [{"filename": "paper.pdf", **record()}]})

    report = build_comparison(
        load_ground_truth(labels_dir),
        load_predictions(prediction),
        load_predictions(prediction),
        baseline_label="V2",
        comparison_label="V3",
    )

    assert report["baseline_label"] == "V2"
    assert report["comparison_label"] == "V3"
