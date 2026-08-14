"""Run an M9 prediction round with a durable checkpoint after every paper.

This runner is intentionally sequential.  It trades some throughput for the
ability to resume after a network or process interruption without sending a
second request for any paper whose result has already been written to disk.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.extractor import Extractor
from app.llm import LLMClient
from app.parser import DocumentParserError, parse_document
from eval.run_predictions import write_predictions


def _load_checkpoint(
    path: Path,
    settings: Settings,
    repair_retries: int,
    label: str = "三级容错（逐篇检查点）",
) -> dict[str, Any]:
    if not path.exists():
        return {
            "evaluation_config": {
                "label": label,
                "model": settings.llm_model,
                "max_repair_retries": repair_retries,
                "transport_retries": settings.llm_max_retries,
                "temperature": 0.0,
            },
            "summary": {"total_files": 0, "success_count": 0, "fail_count": 0, "total_tokens": 0, "duration_ms": 0},
            "results": [],
            "failures": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("results"), list) or not isinstance(payload.get("failures"), list):
        raise ValueError(f"Invalid prediction checkpoint: {path}")
    return payload


def _write_checkpoint(path: Path, payload: dict[str, Any], total_files: int, duration_ms: int) -> None:
    payload["summary"] = {
        "total_files": total_files,
        "success_count": len(payload["results"]),
        "fail_count": len(payload["failures"]),
        "total_tokens": sum(int(item.get("tokens") or 0) for item in payload["results"]),
        "duration_ms": duration_ms,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_checkpointed_predictions(
    files: list[Path], output_path: Path | str, *, repair_retries: int,
    settings: Settings | None = None, label: str = "三级容错（逐篇检查点）",
) -> dict[str, Any]:
    """Extract files sequentially and atomically save after each completed item."""

    active_settings = settings or get_settings()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_checkpoint(target, active_settings, repair_retries, label)
    completed = {
        str(item.get("filename"))
        for item in [*payload["results"], *payload["failures"]]
        if isinstance(item, dict) and item.get("filename")
    }
    started = time.perf_counter()
    with LLMClient(settings=active_settings) as client:
        extractor = Extractor(active_settings, client, max_repair_retries=repair_retries)
        for index, path in enumerate(files, start=1):
            if path.name in completed:
                print(f"[{index}/{len(files)}] SKIP checkpoint {path.name}", flush=True)
                continue
            item_started = time.perf_counter()
            try:
                parsed = parse_document(path)
                result = extractor.extract(parsed.text)
                if result.success and result.record is not None:
                    payload["results"].append(
                        {
                            "filename": path.name,
                            **result.record.model_dump(mode="json"),
                            "retry_count": result.retry_count,
                            "tokens": result.total_tokens,
                            "latency_ms": result.total_latency_ms,
                        }
                    )
                    status = "SUCCESS"
                elif result.failure is not None:
                    payload["failures"].append(
                        {
                            "filename": path.name,
                            "stage": result.failure.stage.value,
                            "error_type": result.failure.error_type,
                            "error_msg": result.failure.error_msg,
                            "retry_count": result.retry_count,
                        }
                    )
                    status = f"FAILED ({result.failure.stage.value})"
                else:
                    raise RuntimeError("Extractor returned neither record nor failure.")
            except (DocumentParserError, OSError, RuntimeError) as exc:
                payload["failures"].append(
                    {"filename": path.name, "stage": "parse", "error_type": type(exc).__name__, "error_msg": str(exc), "retry_count": 0}
                )
                status = "FAILED (parse)"
            _write_checkpoint(target, payload, len(files), round((time.perf_counter() - started) * 1000))
            print(f"[{index}/{len(files)}] {status} {path.name}", flush=True)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a resumable M9 prediction round.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repair-retries", type=int, default=2)
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("This command calls DeepSeek; re-run with --confirm-cost.")
    if args.repair_retries < 0:
        parser.error("--repair-retries must be non-negative.")
    files = sorted(args.input_dir.glob("*.pdf"), key=lambda item: item.name.casefold())
    if not files:
        raise FileNotFoundError(f"No PDFs found in {args.input_dir}")
    result = run_checkpointed_predictions(files, args.output, repair_retries=args.repair_retries)
    print(f"Checkpoint complete: {result['summary']}")


if __name__ == "__main__":
    main()
