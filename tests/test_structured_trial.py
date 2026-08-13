import json

from eval.prepare_structured_trial import prepare_structured_templates
from eval.evaluate_structured_trial import legacy_prediction_to_structured
from eval.structured_trial import (
    ConditionItem,
    ResultItem,
    structured_precision_recall_f1,
)


def test_structured_score_gives_full_credit_for_metric_number_and_unit() -> None:
    expected = [ResultItem(metric="BER", value="2.0e-3", unit=None)]
    actual = [ResultItem(metric="bit error rate", value="2.08e-3", unit=None)]

    score = structured_precision_recall_f1(expected, actual)

    assert score.f1 == 1.0


def test_structured_score_gives_partial_credit_for_same_metric_wrong_value() -> None:
    expected = [ResultItem(metric="BER", value="2.0e-3", unit=None)]
    actual = [ResultItem(metric="BER", value="4.0e-3", unit=None)]

    score = structured_precision_recall_f1(expected, actual)

    assert score.precision == 0.5
    assert score.recall == 0.5
    assert score.f1 == 0.5


def test_structured_score_requires_matching_units() -> None:
    expected = [ConditionItem(name="fiber_length", value="80", unit="km")]
    actual = [ConditionItem(name="fiber_length", value="80", unit="m")]

    assert structured_precision_recall_f1(expected, actual).f1 == 0.5


def test_prepare_structured_templates_never_copies_model_predictions(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": ["paper.pdf"]}), encoding="utf-8")

    created = prepare_structured_templates(manifest, tmp_path / "labels")
    payload = json.loads(created[0].read_text(encoding="utf-8"))

    assert payload["needs_review"] is True
    assert payload["record"] == {"experimental_conditions": [], "main_results": []}


def test_legacy_prediction_projection_splits_values_units_and_conditions() -> None:
    record = legacy_prediction_to_structured(
        {
            "experimental_conditions": ["fiber_length: 80 km"],
            "main_results": ["BER: 2.1e-3 | condition: 80 km SSMF"],
        }
    )

    assert record.experimental_conditions[0].model_dump() == {
        "name": "fiber_length", "value": "80", "unit": "km"
    }
    assert record.main_results[0].model_dump() == {
        "metric": "BER", "value": "2.1e-3", "unit": None, "condition": "80 km SSMF"
    }
