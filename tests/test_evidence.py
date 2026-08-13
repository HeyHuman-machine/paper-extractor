"""V4 证据片段选择测试。"""

from app.evidence import build_evidence_bundle, build_keyword_evidence_bundle


def test_evidence_bundle_keeps_head_method_experiment_and_tail() -> None:
    text = (
        "TITLE: Evidence-aware optical link\nABSTRACT: short summary.\n"
        + ("introduction background.\n" * 180)
        + "We propose a Named Receiver Scheme for optical transmission.\n"
        + ("method detail.\n" * 80)
        + "3. Experimental Results\nBER was 2.1e-3 at -18 dBm over 20 km SSMF.\n"
        + ("result detail.\n" * 180)
        + "CONCLUSION: the setup remains limited to single polarization."
    )

    bundle = build_evidence_bundle(text, max_chars=5000)

    assert len(bundle) <= 5000
    assert "论文开头" in bundle
    assert "方法命名证据" in bundle
    assert "实验 / 仿真 / 结果证据" in bundle
    assert "Named Receiver Scheme" in bundle
    assert "BER was 2.1e-3" in bundle
    assert "single polarization" in bundle


def test_evidence_bundle_returns_short_text_unchanged() -> None:
    assert build_evidence_bundle("short paper", max_chars=800) == "short paper"


def test_keyword_evidence_bundle_keeps_measurements_without_section_heading() -> None:
    text = (
        "TITLE: Keyword evidence link\nABSTRACT: summary.\n"
        + ("background discussion.\n" * 300)
        + "A 16-Gbaud 16QAM signal was sent over 20 km SSMF at -18 dBm.\n"
        + ("unstructured extracted text.\n" * 120)
        + "The BER was below 3.8e-3 HD-FEC with 1.5 dB power penalty.\n"
        + ("more text.\n" * 250)
        + "CONCLUSION: limited to single polarization."
    )

    bundle = build_keyword_evidence_bundle(text, max_chars=5000)

    assert len(bundle) <= 5000
    assert "条件数值证据" in bundle
    assert "结果指标证据" in bundle
    assert "16-Gbaud" in bundle
    assert "20 km" in bundle
    assert "BER was below" in bundle
    assert "single polarization" in bundle
