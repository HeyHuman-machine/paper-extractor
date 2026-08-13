"""用同一批论文生成无修正重试与三级容错两轮 M9 预测。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.extractor import Extractor
from app.llm import LLMClient
from app.models import BatchResult
from app.pipeline import discover_documents, run_batch


def run_prediction_round(
    files: list[Path],
    settings: Settings,
    *,
    max_repair_retries: int,
    evidence_aware: bool = False,
    evidence_strategy: str | None = None,
) -> BatchResult:
    """运行一轮预测；HTTP 重试保持不变，只控制 M3 内容修正次数。"""

    with LLMClient(settings=settings) as client:
        extractor = Extractor(
            settings,
            client,
            max_repair_retries=max_repair_retries,
            evidence_aware=evidence_aware,
            evidence_strategy=evidence_strategy,
        )
        return run_batch(
            files,
            concurrency=settings.batch_concurrency,
            settings=settings,
            extractor=extractor,
            on_progress=lambda current, total, filename, status: print(
                f"[{current}/{total}] {status.upper():7} {filename}", flush=True
            ),
        )


def write_predictions(
    batch: BatchResult,
    path: Path | str,
    *,
    label: str,
    max_repair_retries: int,
    settings: Settings,
) -> Path:
    """把批次写成评测可读取的 JSON，不污染正式 SQLite。"""

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for item in batch.files:
        if item.success and item.record is not None:
            results.append(
                {
                    "filename": item.filename,
                    **item.record.model_dump(mode="json"),
                    "retry_count": item.retry_count,
                    "tokens": item.total_tokens,
                    "latency_ms": item.duration_ms,
                }
            )
        elif item.failure is not None:
            failures.append(
                {
                    "filename": item.filename,
                    "stage": item.failure.stage.value,
                    "error_type": item.failure.error_type,
                    "error_msg": item.failure.error_msg,
                    "retry_count": item.retry_count,
                }
            )
    payload = {
        "evaluation_config": {
            "label": label,
            "model": settings.llm_model,
            "max_repair_retries": max_repair_retries,
            "transport_retries": settings.llm_max_retries,
            "temperature": 0.0,
        },
        "summary": {
            "total_files": batch.total_files,
            "success_count": batch.success_count,
            "fail_count": batch.fail_count,
            "total_tokens": batch.total_tokens,
            "duration_ms": batch.duration_ms,
        },
        "results": results,
        "failures": failures,
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 M9 两轮真实预测")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("eval/predictions"))
    parser.add_argument("--repair-retries", type=int, default=2)
    parser.add_argument(
        "--confirm-cost",
        action="store_true",
        help="确认会对同一批论文调用 DeepSeek 两轮",
    )
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("此命令会真实调用 DeepSeek 两轮；确认后加 --confirm-cost")
    if args.repair_retries < 1:
        parser.error("--repair-retries 必须大于等于 1")

    settings = get_settings()
    files = discover_documents(args.input_dir or settings.input_dir)
    if not files:
        raise FileNotFoundError("评测输入目录没有 PDF / DOCX")
    print(f"同一批 {len(files)} 篇论文将运行两轮。")
    print("第一轮：无内容修正重试")
    baseline = run_prediction_round(files, settings, max_repair_retries=0)
    write_predictions(
        baseline,
        args.output_dir / "no_retry.json",
        label="无内容修正重试",
        max_repair_retries=0,
        settings=settings,
    )
    print("第二轮：三级容错")
    robust = run_prediction_round(
        files,
        settings,
        max_repair_retries=args.repair_retries,
    )
    write_predictions(
        robust,
        args.output_dir / "with_retries.json",
        label="三级容错",
        max_repair_retries=args.repair_retries,
        settings=settings,
    )
    print(f"预测已保存：{args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
