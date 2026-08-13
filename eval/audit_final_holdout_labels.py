"""Audit final-holdout label drafts against the locally frozen PDF corpus.

The audit is deliberately conservative: it checks schema validity, provenance,
title presence and numeric claims in experiment/result lists.  A passing audit
is evidence for a reviewer, not an automatic substitute for review.  Promotion
to ``needs_review=false`` is intentionally a separate explicit operation.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import PaperRecord
from app.parser import parse_document


NUMBER_WITH_UNIT = re.compile(
    r"(?<![a-z0-9])-?\d+(?:\.\d+)?\s*(?:gb/s|tb/s|gbaud|ghz|thz|nm|km|m|db|%|pam-?\d|qam-?\d)",
    re.IGNORECASE,
)


def _normal(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _page_texts(pdf_path: Path) -> list[str]:
    return parse_document(pdf_path).pages


def _pages_containing(pages: list[str], phrase: str) -> list[int]:
    normalized_phrase = _normal(phrase)
    if len(normalized_phrase) < 6:
        return []
    matches = [index + 1 for index, text in enumerate(pages) if normalized_phrase in _normal(text)]
    if matches:
        return matches
    # A PDF title block may use a near-identical venue word (for example,
    # ``Systems`` versus ``Communications``).  Do not silently accept it:
    # return the page as a reviewer hint but leave the title mismatch visible.
    return []


def _numeric_evidence(pages: list[str], statement: str) -> list[int]:
    facts = [_normal(value) for value in NUMBER_WITH_UNIT.findall(statement)]
    if not facts:
        return []
    matched: list[int] = []
    for index, page in enumerate(pages, 1):
        normalized = _normal(page)
        if all(fact in normalized for fact in facts):
            matched.append(index)
    return matched


@dataclass(frozen=True)
class AuditResult:
    filename: str
    passed: bool
    problems: list[str]
    evidence: dict[str, Any]


def audit_label(label_path: Path, pdf_dir: Path) -> AuditResult:
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    filename = str(payload["filename"])
    record = PaperRecord.model_validate(payload["record"])
    pdf_path = pdf_dir / filename
    if not pdf_path.exists():
        return AuditResult(filename, False, ["local PDF is missing"], {})
    pages = _page_texts(pdf_path)
    problems: list[str] = []
    title_pages = _pages_containing(pages, record.title)
    if not title_pages:
        problems.append("title was not found in extracted PDF text")

    field_evidence: dict[str, list[dict[str, Any]]] = {}
    for field_name in ("experimental_conditions", "main_results"):
        entries: list[dict[str, Any]] = []
        for statement in getattr(record, field_name):
            numeric_pages = _numeric_evidence(pages, statement)
            entries.append(
                {
                    "statement": statement,
                    "numeric_fact_pages": numeric_pages,
                }
            )
            if NUMBER_WITH_UNIT.search(statement) and not numeric_pages:
                problems.append(f"{field_name} numeric claim has no PDF match: {statement}")
        field_evidence[field_name] = entries

    evidence = {
        "pdf_page_count": len(pages),
        "title_pages": title_pages,
        "numeric_claim_audit": field_evidence,
    }
    return AuditResult(filename, not problems, problems, evidence)


def audit_directory(label_dir: Path | str, pdf_dir: Path | str, output_path: Path | str) -> dict[str, Any]:
    labels = sorted(Path(label_dir).glob("*.json"))
    results: list[AuditResult] = []
    for label in labels:
        try:
            results.append(audit_label(label, Path(pdf_dir)))
        except Exception as exc:  # Keep one bad draft from blocking visibility of the rest.
            results.append(AuditResult(label.name, False, [f"audit error: {type(exc).__name__}: {exc}"], {}))
    report = {
        "label_count": len(results),
        "passed_count": sum(item.passed for item in results),
        "failed_count": sum(not item.passed for item in results),
        "results": [
            {"filename": item.filename, "passed": item.passed, "problems": item.problems, "evidence": item.evidence}
            for item in results
        ],
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit final-holdout AI drafts against local PDFs.")
    parser.add_argument("--label-dir", type=Path, default=Path("eval/ground_truth_final_holdout"))
    parser.add_argument("--pdf-dir", type=Path, default=Path("literature/optical-communications/final_holdout"))
    parser.add_argument("--output", type=Path, default=Path("eval/output/final-holdout-label-audit.json"))
    args = parser.parse_args()
    report = audit_directory(args.label_dir, args.pdf_dir, args.output)
    print(f"Audited {report['label_count']} labels: {report['passed_count']} passed, {report['failed_count']} require correction.")
    for item in report["results"]:
        if not item["passed"]:
            print(f"[CHECK] {item['filename']}: {' | '.join(item['problems'])}")


if __name__ == "__main__":
    main()
