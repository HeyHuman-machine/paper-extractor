import json
from pathlib import Path

from eval.prepare_final_holdout_labels import create_label_drafts


def test_final_holdout_manifest_has_30_unique_arxiv_ids() -> None:
    manifest_path = Path("eval/final_holdout_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    papers = manifest["papers"]

    assert manifest["dataset_id"] == "final-holdout-v1"
    assert len(papers) == 30
    assert len({paper["arxiv_id"] for paper in papers}) == 30
    assert len({paper["filename"] for paper in papers}) == 30


def test_final_holdout_label_drafts_only_prefill_manifest_metadata(tmp_path: Path) -> None:
    created = create_label_drafts("eval/final_holdout_manifest.json", tmp_path)

    assert len(created) == 30
    draft = json.loads(created[0].read_text(encoding="utf-8"))
    assert draft["needs_review"] is True
    assert draft["annotation_meta"]["split"] == "final_holdout"
    assert draft["record"]["title"]
    assert draft["record"]["authors"] == []
    assert draft["record"]["problem"] == ""
    assert draft["record"]["experimental_conditions"] == []
    assert draft["record"]["main_results"] == []
