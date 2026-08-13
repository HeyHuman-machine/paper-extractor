import json

from eval.audit_final_holdout_labels import audit_directory
from eval.promote_verified_final_holdout_labels import promote_verified_labels


def test_audit_reports_missing_local_pdf(tmp_path):
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "paper.json").write_text(
        json.dumps(
            {
                "filename": "paper.pdf",
                "needs_review": True,
                "record": {
                    "title": "Paper",
                    "authors": ["Author"],
                    "year": 2024,
                    "venue": None,
                    "doc_type": "preprint",
                    "problem": "Problem",
                    "method_name": None,
                    "experimental_conditions": [],
                    "main_results": [],
                    "limitations": None,
                    "summary": "Summary",
                },
            }
        ),
        encoding="utf-8",
    )

    report = audit_directory(labels, tmp_path / "pdfs", tmp_path / "audit.json")

    assert report["label_count"] == 1
    assert report["failed_count"] == 1
    assert report["results"][0]["problems"] == ["local PDF is missing"]


def test_promotion_refuses_an_incomplete_audit(tmp_path):
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"label_count": 30, "failed_count": 1, "results": []}), encoding="utf-8")

    try:
        promote_verified_labels(tmp_path, audit)
    except ValueError as exc:
        assert "Refusing promotion" in str(exc)
    else:
        raise AssertionError("Promotion must reject an audit with failures.")
