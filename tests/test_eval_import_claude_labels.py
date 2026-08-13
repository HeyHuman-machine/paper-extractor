import json

from eval.import_claude_labels import import_claude_labels


def _record(summary: str) -> dict:
    return {
        "title": "A paper",
        "authors": ["Author"],
        "year": 2026,
        "venue": "Optics Express",
        "doc_type": "journal_article",
        "problem": "A concise problem.",
        "method_name": None,
        "experimental_conditions": [],
        "main_results": [],
        "limitations": None,
        "summary": summary,
        "": "Claude extra key",
    }


def test_imports_concatenated_arrays_and_normalizes_filename(tmp_path):
    input_dir = tmp_path / "papers"
    input_dir.mkdir()
    (input_dir / "07-example-paper.pdf").write_bytes(b"placeholder")
    source = tmp_path / "claude.txt"
    payload = {
        "filename": "07examplepaper.pdf",
        "needs_review": True,
        "annotation_meta": {"human_attention_fields": ["year"]},
        "record": _record("一句话。" * 250),
        "evidence": {"bibliography": [{"pdf_page": 1}]},
    }
    source.write_text(json.dumps([payload]) + "\n" + json.dumps([]), encoding="utf-8")

    created = import_claude_labels(source, input_dir, tmp_path / "labels")

    assert len(created) == 1
    label = json.loads(created[0].read_text(encoding="utf-8"))
    assert label["filename"] == "07-example-paper.pdf"
    assert label["needs_review"] is True
    assert label["annotation_meta"]["source_filename"] == "07examplepaper.pdf"
    assert len(label["record"]["summary"]) <= 400
    assert "" not in label["record"]
