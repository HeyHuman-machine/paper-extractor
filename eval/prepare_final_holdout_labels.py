"""Create independently reviewable label drafts for the frozen final holdout.

Only manifest-backed metadata is prefilled. Research-content fields stay empty
so that no answer is silently invented before a PDF-based annotation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval.metrics import safe_label_filename


DEFAULT_MANIFEST = Path(__file__).with_name("final_holdout_manifest.json")
DEFAULT_OUTPUT = Path("eval/ground_truth_final_holdout")


def create_label_drafts(manifest_path: Path | str, output_dir: Path | str) -> list[Path]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    papers = manifest.get("papers")
    if not isinstance(papers, list):
        raise ValueError("Final-holdout manifest must contain a papers list.")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for paper in papers:
        if not isinstance(paper, dict):
            raise ValueError("Each final-holdout paper must be an object.")
        filename = paper.get("filename")
        title = paper.get("title")
        year = paper.get("year")
        arxiv_id = paper.get("arxiv_id")
        if not all(isinstance(value, str) and value.strip() for value in (filename, title, arxiv_id)):
            raise ValueError("Each paper needs filename, title, and arxiv_id.")
        if not isinstance(year, int):
            raise ValueError("Each paper needs an integer year.")

        target = destination / safe_label_filename(filename)
        if target.exists():
            continue
        draft: dict[str, Any] = {
            "filename": filename,
            "needs_review": True,
            "annotation_meta": {
                "split": "final_holdout",
                "review_status": "metadata_prefilled_pending_pdf_annotation",
                "reviewed_by": None,
                "reviewed_at": None,
                "source": f"https://arxiv.org/abs/{arxiv_id}",
                "note": (
                    "标题、年份与来源来自冻结清单；其余字段必须对照 PDF 完成独立标注。"
                    "任何 AI 初标均不能替代人工金标准。"
                ),
            },
            "record": {
                "title": title,
                "authors": [],
                "year": year,
                "venue": "arXiv preprint",
                "doc_type": "preprint",
                "problem": "",
                "method_name": None,
                "experimental_conditions": [],
                "main_results": [],
                "limitations": None,
                "summary": "",
            },
            "evidence": {},
        }
        target.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(target)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Create final-holdout metadata label drafts.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    created = create_label_drafts(args.manifest, args.output_dir)
    print(f"Created {len(created)} final-holdout label drafts; existing files were not overwritten.")


if __name__ == "__main__":
    main()
