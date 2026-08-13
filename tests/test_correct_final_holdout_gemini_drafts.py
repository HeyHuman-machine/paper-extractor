import json

from eval.correct_final_holdout_gemini_drafts import apply_confirmed_corrections


def test_applies_only_known_pdf_confirmed_corrections(tmp_path):
    for filename in (
        "F02-autoencoder-pam-imdd.pdf",
        "F22-jones-space-field-recovery.pdf",
        "F25-dual-polarization-field-reconstruction.pdf",
    ):
        (tmp_path / f"{filename.removesuffix('.pdf')}.json").write_text(
            json.dumps({"record": {}, "annotation_meta": {}, "evidence": {}}), encoding="utf-8"
        )

    changed = apply_confirmed_corrections(tmp_path)

    assert len(changed) == 3
    f02 = json.loads((tmp_path / "F02-autoencoder-pam-imdd.json").read_text(encoding="utf-8"))
    assert "4-8 km" in f02["record"]["main_results"][1]
    f25 = json.loads((tmp_path / "F25-dual-polarization-field-reconstruction.json").read_text(encoding="utf-8"))
    assert f25["record"]["title"].endswith("Communications")
    assert len(f25["record"]["authors"]) == 6
