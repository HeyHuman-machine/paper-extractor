from eval.diagnose_field_errors import _markdown, build_diagnosis
from eval.metrics import safe_label_filename

from test_eval_metrics import record


def test_diagnosis_lists_only_nonperfect_papers(tmp_path):
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()
    label = {
        "filename": "paper.pdf",
        "needs_review": False,
        "record": record().model_dump(mode="json"),
    }
    (labels_dir / safe_label_filename("paper.pdf")).write_text(
        __import__("json").dumps(label), encoding="utf-8"
    )
    base = tmp_path / "v1.json"
    improved = tmp_path / "v2.json"
    base.write_text(
        __import__("json").dumps({"results": [{"filename": "paper.pdf", **record().model_dump(mode="json"), "year": 2024}]}),
        encoding="utf-8",
    )
    improved.write_text(
        __import__("json").dumps({"results": [{"filename": "paper.pdf", **record().model_dump(mode="json")}]}),
        encoding="utf-8",
    )

    diagnosis = build_diagnosis(
        labels_dir,
        base,
        improved,
        baseline_label="V2",
        comparison_label="V3",
    )
    markdown = _markdown(diagnosis)

    assert "| paper.pdf | 0.00% | 100.00% | 改善 |" in markdown
    assert "# V2-V3 字段误差诊断" in markdown
    assert "标题" in markdown
