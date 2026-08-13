import json

from eval.import_external_ai_drafts import import_external_ai_drafts


def _record() -> dict:
    return {
        "title": "Frozen paper",
        "authors": ["Author"],
        "year": 2024,
        "venue": "arXiv preprint",
        "doc_type": "preprint",
        "problem": "A concise research problem.",
        "method_name": "A method",
        "experimental_conditions": ["10 km PAM-4"],
        "main_results": ["2 dB gain"],
        "limitations": None,
        "summary": "A concise summary.",
    }


def test_import_external_drafts_strips_preamble_and_keeps_pending(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"papers": [{"id": "F01", "filename": "F01-frozen-paper.pdf"}]}),
        encoding="utf-8",
    )
    source = tmp_path / "gemini.txt"
    source.write_text(
        "download failed; generated output follows\n"
        + json.dumps([{"filename": "F01-Frozen-Paper.pdf", "needs_review": False, "record": _record()}]),
        encoding="utf-8",
    )

    created = import_external_ai_drafts([source], manifest, tmp_path / "labels", reviewer_name="Gemini")

    assert len(created) == 1
    imported = json.loads(created[0].read_text(encoding="utf-8"))
    assert imported["filename"] == "F01-frozen-paper.pdf"
    assert imported["needs_review"] is True
    assert imported["annotation_meta"]["source_filename"] == "F01-Frozen-Paper.pdf"
