"""V6 字段级混合验证：保留 V2，仅精修 ``main_results``。"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.llm import LLMClient
from app.parser import parse_document
from app.pipeline import discover_documents
from app.result_refiner import ResultRefiner


def build_hybrid_prediction(
    baseline_payload: dict[str, Any],
    files: list[Path],
    *,
    max_retries: int,
) -> dict[str, Any]:
    """将成功的精修结果覆盖 V2 的 ``main_results``；失败时原样回退。"""

    settings = get_settings()
    baseline_by_filename = {
        str(item["filename"]): item
        for item in baseline_payload.get("results", [])
        if isinstance(item, dict) and item.get("filename")
    }
    missing = [path.name for path in files if path.name not in baseline_by_filename]
    if missing:
        raise ValueError(f"基线预测缺少论文：{', '.join(missing)}")

    refinements: dict[str, dict[str, Any]] = {}
    with LLMClient(settings=settings) as client:
        refiner = ResultRefiner(client, max_retries=max_retries)
        with ThreadPoolExecutor(max_workers=settings.batch_concurrency) as executor:
            futures = {
                executor.submit(
                    _refine_one, path, refiner, settings.extract_max_chars
                ): path.name
                for path in files
            }
            for current, future in enumerate(as_completed(futures), start=1):
                filename = futures[future]
                refinements[filename] = future.result()
                status = "REFINED" if refinements[filename]["success"] else "FALLBACK"
                print(f"[{current}/{len(files)}] {status:8} {filename}", flush=True)

    combined_results: list[dict[str, Any]] = []
    total_refinement_tokens = 0
    for path in files:
        original = dict(baseline_by_filename[path.name])
        refinement = refinements[path.name]
        total_refinement_tokens += refinement["tokens"]
        if refinement["success"]:
            original["main_results"] = refinement["main_results"]
            original["result_refinement"] = {
                "used": True,
                "tokens": refinement["tokens"],
                "latency_ms": refinement["latency_ms"],
                "retry_count": refinement["retry_count"],
            }
        else:
            original["result_refinement"] = {
                "used": False,
                "fallback": "保留 V2 main_results",
                "error": refinement["error"],
            }
        combined_results.append(original)

    baseline_summary = baseline_payload.get("summary", {})
    return {
        "evaluation_config": {
            "label": "V6 字段级混合：V2 + 结果关键词精修",
            "model": settings.llm_model,
            "baseline": "V2 原子化 Prompt 开发集验证",
            "refined_field": "main_results",
            "result_refinement_retries": max_retries,
            "temperature": 0.0,
        },
        "summary": {
            "total_files": len(files),
            "success_count": len(combined_results),
            "fail_count": 0,
            "baseline_tokens": int(baseline_summary.get("total_tokens", 0)),
            "result_refinement_tokens": total_refinement_tokens,
            "total_tokens": int(baseline_summary.get("total_tokens", 0)) + total_refinement_tokens,
        },
        "results": combined_results,
        "failures": [],
    }


def _refine_one(path: Path, refiner: ResultRefiner, max_chars: int) -> dict[str, Any]:
    try:
        parsed = parse_document(path)
        result = refiner.refine(parsed.text, max_chars)
        return {
            "success": result.success,
            "main_results": result.main_results,
            "tokens": result.tokens,
            "latency_ms": result.latency_ms,
            "retry_count": result.retry_count,
            "error": result.error,
        }
    except Exception as exc:
        return {
            "success": False,
            "main_results": None,
            "tokens": 0,
            "latency_ms": 0,
            "retry_count": 0,
            "error": f"{type(exc).__name__}: {str(exc)[:700]}",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 V6 结果字段混合开发集验证")
    parser.add_argument(
        "--input-dir", type=Path, default=Path("literature/optical-communications/seed")
    )
    parser.add_argument(
        "--baseline", type=Path, default=Path("eval/predictions/v2-development/predictions.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("eval/predictions/v6-development/predictions.json")
    )
    parser.add_argument("--result-retries", type=int, default=1)
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("此命令会调用 LLM 精修结果字段；确认后加 --confirm-cost")
    if args.result_retries < 0:
        parser.error("--result-retries 不能小于 0")
    if not args.baseline.is_file():
        raise FileNotFoundError(f"V2 基线预测不存在：{args.baseline}")
    files = discover_documents(args.input_dir)
    if not files:
        raise FileNotFoundError("开发集目录没有 PDF / DOCX")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    print(f"V6：保留 V2，精修 {len(files)} 篇的 main_results", flush=True)
    payload = build_hybrid_prediction(baseline, files, max_retries=args.result_retries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"预测已保存：{args.output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
