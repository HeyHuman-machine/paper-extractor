from eval.metrics import calibrated_method_match, calibrated_method_match_detail, evaluate_records


def test_calibrated_method_match_ignores_parenthetical_explanation_and_suffix() -> None:
    assert calibrated_method_match(
        "Enhanced Kramers-Kronig receiver (negative-peak clipping in correction path)",
        "Enhanced Kramers-Kronig receiver with negative-peak clipping",
    )


def test_calibrated_method_match_accepts_explicit_acronym_expansion() -> None:
    matched, reason = calibrated_method_match_detail(
        "FASCD",
        "Filter-Assisted Self-Coherent Detection",
    )
    assert matched is True
    assert reason == "explicit_acronym_expansion"


def test_calibrated_method_match_rejects_component_for_composite_method() -> None:
    assert not calibrated_method_match(
        "Kramers-Kronig receiver with digitally added carrier combined with digital resolution enhancer (DRE)",
        "Digital Resolution Enhancer (DRE)",
    )


def test_calibrated_method_match_keeps_parenthetical_composite_method() -> None:
    assert not calibrated_method_match(
        "Kramers-Kronig scheme (assessed together with linearization filters and SSBI cancellation)",
        "Kramers-Kronig scheme",
    )


def test_evaluate_records_accepts_parallel_method_matcher() -> None:
    from app.models import PaperRecord

    truth = {
        "paper.pdf": PaperRecord(
            method_name="FASCD",
            title="t",
            authors=["A"],
            year=None,
            venue=None,
            doc_type="other",
            problem="p",
            experimental_conditions=[],
            main_results=[],
            limitations=None,
            summary="s",
        )
    }
    prediction = {"paper.pdf": {"method_name": "Filter-Assisted Self-Coherent Detection"}}
    baseline = evaluate_records(truth, prediction)
    calibrated = evaluate_records(truth, prediction, method_name_matcher=calibrated_method_match)
    assert baseline["fields"]["method_name"]["score"] == 0.0
    assert calibrated["fields"]["method_name"]["score"] == 1.0
