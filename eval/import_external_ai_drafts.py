"""Import external AI label drafts without promoting them to gold labels.

External chat tools often prepend explanations or failed download logs before a
JSON array, and may change the display case of a PDF filename.  This importer
keeps that source traceability but always maps records back to the frozen
final-holdout manifest and forces ``needs_review`` to remain true.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from app.models import PaperRecord
from eval.metrics import safe_label_filename


def _find_record_arrays(source: Path) -> list[dict[str, Any]]:
    """Return embedded JSON arrays whose items look like label payloads."""

    content = source.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    signatures: set[tuple[str, ...]] = set()
    for match in re.finditer(r"\[", content):
        try:
            payload, _ = decoder.raw_decode(content, match.start())
        except json.JSONDecodeError:
            continue
        if not (
            isinstance(payload, list)
            and payload
            and all(isinstance(item, dict) for item in payload)
            and all("filename" in item and "record" in item for item in payload)
        ):
            continue
        signature = tuple(str(item["filename"]) for item in payload)
        if signature not in signatures:
            records.extend(payload)
            signatures.add(signature)
    if not records:
        raise ValueError(f"{source} does not contain a label JSON array.")
    return records


def _paper_id(value: str) -> str:
    match = re.search(r"\b(F\d{2})\b", value, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot identify final-holdout ID from: {value}")
    return match.group(1).upper()


def import_external_ai_drafts(
    sources: list[Path | str],
    manifest_path: Path | str,
    output_dir: Path | str,
    *,
    reviewer_name: str,
    overwrite: bool = False,
) -> list[Path]:
    """Validate and import every frozen-holdout record as an AI draft."""

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    expected = {str(item["id"]): item for item in manifest["papers"]}
    incoming: dict[str, tuple[dict[str, Any], str]] = {}
    for source in (Path(item) for item in sources):
        for payload in _find_record_arrays(source):
            identifier = _paper_id(str(payload["filename"]))
            if identifier not in expected:
                raise ValueError(f"Unexpected final-holdout ID: {identifier}")
            if identifier in incoming:
                raise ValueError(f"Duplicate external label for {identifier}")
            incoming[identifier] = (payload, source.name)
    missing = sorted(set(expected) - set(incoming))
    if missing:
        raise ValueError(f"External labels are missing: {', '.join(missing)}")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for identifier, paper in expected.items():
        payload, source_name = incoming[identifier]
        record = PaperRecord.model_validate(payload["record"]).model_dump(mode="json")
        metadata = dict(payload.get("annotation_meta") or {})
        metadata.update(
            {
                "split": "final_holdout",
                "review_status": "external_ai_draft_pending_local_pdf_verification",
                "reviewed_by": reviewer_name,
                "reviewed_at": str(date.today()),
                "source_filename": str(payload["filename"]),
                "source_artifact": source_name,
                "note": (
                    "Imported external-AI draft. It remains excluded from final M9 "
                    "scoring until its local PDF evidence is verified."
                ),
            }
        )
        target = destination / safe_label_filename(str(paper["filename"]))
        if target.exists() and not overwrite:
            continue
        result = {
            "filename": paper["filename"],
            "needs_review": True,
            "annotation_meta": metadata,
            "record": record,
            "evidence": dict(payload.get("evidence") or {}),
        }
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(target)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Import external final-holdout AI drafts safely.")
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("eval/final_holdout_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("eval/ground_truth_final_holdout"))
    parser.add_argument("--reviewer-name", default="external AI")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    imported = import_external_ai_drafts(
        args.sources,
        args.manifest,
        args.output_dir,
        reviewer_name=args.reviewer_name,
        overwrite=args.overwrite,
    )
    print(f"Imported {len(imported)} external AI drafts; all remain needs_review=true.")


if __name__ == "__main__":
    main()
