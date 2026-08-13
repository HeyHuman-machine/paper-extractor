import json

from eval.diagnostics import build_diagnostics, write_diagnostics
from eval.metrics import safe_label_filename

from test_eval_metrics import record


def test_diagnostics_exports_raw_and_human_category_template(tmp_path):
    labels = tmp_path / "labels"
    labels.mkdir()
    truth = record(method_name="CADD", experimental_conditions=["baud_rate: 25 Gbaud"], main_results=["BER: 1e-3"])
    (labels / safe_label_filename("paper.pdf")).write_text(json.dumps({"filename": "paper.pdf", "needs_review": False, "record": truth.model_dump(mode="json")}), encoding="utf-8")
    prediction = tmp_path / "predictions.json"
    prediction.write_text(json.dumps({"results": [{"filename": "paper.pdf", **truth.model_dump(mode="json")}]}), encoding="utf-8")

    diagnosis = build_diagnostics(labels, prediction)
    paths = write_diagnostics(diagnosis, tmp_path / "out", metrics_source="eval/metrics.py")

    assert paths["raw_csv"].exists()
    assert "失败归类" in paths["failures"].read_text(encoding="utf-8")
    assert diagnosis["field_summary"]["main_results"]["f1"] == 1.0
