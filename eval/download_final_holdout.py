"""Download the frozen final holdout corpus from its public arXiv sources.

The script deliberately only downloads and validates PDF files.  It never
creates labels, because an evaluation label must be independently reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(__file__).with_name("final_holdout_manifest.json")
DEFAULT_DESTINATION = PROJECT_ROOT / "literature" / "optical-communications" / "final_holdout"
MIN_PDF_BYTES = 10_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the final holdout arXiv PDF corpus.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--overwrite", action="store_true", help="Redownload files that already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Show URLs without downloading.")
    parser.add_argument("--delay-seconds", type=float, default=3.0, help="Delay between network requests.")
    return parser.parse_args()


def arxiv_pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def validate_pdf(content: bytes, source: str) -> None:
    if len(content) < MIN_PDF_BYTES:
        raise ValueError(f"Downloaded file is too small ({len(content)} bytes): {source}")
    if not content.startswith(b"%PDF-"):
        raise ValueError(f"Downloaded content is not a PDF: {source}")


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "paper-extractor-final-holdout/1.0"})
    with urlopen(request, timeout=90) as response:  # noqa: S310 - URL comes from a fixed arXiv pattern.
        return response.read()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    papers = manifest["papers"]
    validation_rows: list[dict[str, object]] = []

    for index, paper in enumerate(papers, start=1):
        destination = args.destination / paper["filename"]
        url = arxiv_pdf_url(paper["arxiv_id"])
        if args.dry_run:
            print(f"[DRY RUN] {paper['id']}: {url} -> {destination}")
            continue
        args.destination.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not args.overwrite:
            content = destination.read_bytes()
            validate_pdf(content, str(destination))
            print(f"[SKIP] {paper['id']}: existing validated PDF")
        else:
            content = download(url)
            validate_pdf(content, url)
            destination.write_bytes(content)
            print(f"[OK] {paper['id']}: {len(content):,} bytes")
        validation_rows.append(
            {
                "id": paper["id"],
                "filename": paper["filename"],
                "arxiv_id": paper["arxiv_id"],
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
        if index < len(papers):
            time.sleep(args.delay_seconds)

    if not args.dry_run:
        report_path = args.destination / "validation-report.json"
        report_path.write_text(
            json.dumps(
                {"dataset_id": manifest["dataset_id"], "files": validation_rows},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Validation report: {report_path}")


if __name__ == "__main__":
    main()
