"""Promote final-holdout labels only after a complete local-PDF audit passes."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


def promote_verified_labels(
    label_dir: Path | str,
    audit_path: Path | str,
    *,
    expected_count: int = 30,
) -> list[Path]:
    """Set ``needs_review`` false only for a complete, all-passing audit."""

    report = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    if report.get("label_count") != expected_count or report.get("failed_count") != 0:
        raise ValueError(
            "Refusing promotion: the final-holdout audit is incomplete or still has failures."
        )
    evidence_by_filename = {item["filename"]: item["evidence"] for item in report["results"]}
    labels = sorted(Path(label_dir).glob("*.json"))
    if len(labels) != expected_count:
        raise ValueError(f"Expected {expected_count} labels, found {len(labels)}.")

    promoted: list[Path] = []
    for path in labels:
        payload = json.loads(path.read_text(encoding="utf-8"))
        filename = str(payload["filename"])
        if filename not in evidence_by_filename:
            raise ValueError(f"Audit report has no record for {filename}.")
        metadata = dict(payload.get("annotation_meta") or {})
        metadata.update(
            {
                "review_status": "local_pdf_verified_final_holdout_label",
                "reviewed_by": "Codex local PDF verification",
                "reviewed_at": str(date.today()),
                "pages_checked": f"full PDF ({evidence_by_filename[filename]['pdf_page_count']} pages)",
                "note": (
                    "External-AI draft was corrected where needed and verified against "
                    "the locally frozen PDF before final-holdout scoring."
                ),
            }
        )
        evidence = dict(payload.get("evidence") or {})
        evidence["local_pdf_verification"] = evidence_by_filename[filename]
        payload["needs_review"] = False
        payload["annotation_meta"] = metadata
        payload["evidence"] = evidence
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        promoted.append(path)
    return promoted


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote fully audited final-holdout labels.")
    parser.add_argument("--label-dir", type=Path, default=Path("eval/ground_truth_final_holdout"))
    parser.add_argument("--audit", type=Path, default=Path("eval/output/final-holdout-label-audit.json"))
    args = parser.parse_args()
    promoted = promote_verified_labels(args.label_dir, args.audit)
    print(f"Promoted {len(promoted)} local-PDF-verified final-holdout labels.")


if __name__ == "__main__":
    main()
