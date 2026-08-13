"""B2 结构化输出试点的真实预测与评分入口（默认不调用 API）。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.extractor import JSONExtractionError, parse_json_object
from app.llm import LLMClient, LLMError
from app.parser import DocumentParserError, parse_document, smart_truncate
from eval.structured_trial import (
    StructuredFieldRecord,
    append_structured_repair_message,
    build_structured_trial_messages,
)


def load_manifest(manifest_path: Path | str) -> list[str]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, list) or not all(isinstance(name, str) and name.strip() for name in files):
        raise ValueError("B2 清单必须包含非空 files 数组")
    return files


def run_structured_trial(
    input_dir: Path | str,
    filenames: list[str],
    *,
    repair_retries: int,
    checkpoint_path: Path | str | None = None,
    retry_failures: bool = False,
) -> dict[str, Any]:
    """对清单内论文各抽取一次结构化字段，逐篇保存检查点。

    网络调用可能耗时或异常中断。每处理完一篇就写一次 JSON 检查点；下次使用
    相同路径运行时会跳过已有成功/失败记录，避免重复消耗 API Token。
    """

    settings = get_settings()
    root = Path(input_dir)
    checkpoint = Path(checkpoint_path) if checkpoint_path is not None else None
    payload = _load_checkpoint(checkpoint, settings, repair_retries)
    results: list[dict[str, Any]] = payload["results"]
    failures: list[dict[str, Any]] = payload["failures"]
    completed = {
        item["filename"]
        for item in results
        if isinstance(item, dict) and isinstance(item.get("filename"), str)
    }
    if retry_failures:
        failures = []
    else:
        completed.update(
            item["filename"]
            for item in failures
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        )
    with LLMClient(settings=settings) as client:
        for index, filename in enumerate(filenames, start=1):
            if filename in completed:
                print(f"[{index}/{len(filenames)}] SKIP (checkpoint) {filename}", flush=True)
                continue
            path = root / filename
            started = time.perf_counter()
            try:
                parsed = parse_document(path)
                messages = build_structured_trial_messages(
                    smart_truncate(parsed.text, settings.extract_max_chars)
                )
                total_tokens = 0
                for attempt in range(repair_retries + 1):
                    response = client.chat(messages, max_tokens=1200, temperature=0.0)
                    total_tokens += response.total_tokens
                    raw_output = response.content
                    try:
                        record = StructuredFieldRecord.model_validate(parse_json_object(raw_output))
                    except (JSONExtractionError, ValidationError) as exc:
                        if attempt >= repair_retries:
                            raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
                        messages = append_structured_repair_message(messages, raw_output, str(exc))
                        continue
                    results.append(
                        {
                            "filename": filename,
                            "record": record.model_dump(mode="json"),
                            "repair_count": attempt,
                            "tokens": total_tokens,
                            "latency_ms": round((time.perf_counter() - started) * 1000),
                        }
                    )
                    break
            except Exception as exc:  # 单篇兜底：不丢检查点，也不让整批中断。
                failures.append(
                    {
                        "filename": filename,
                        "error_type": type(exc).__name__,
                        "error_msg": str(exc)[:1500],
                        "latency_ms": round((time.perf_counter() - started) * 1000),
                    }
                )
            payload = _build_payload(settings, repair_retries, filenames, results, failures)
            _write_checkpoint(checkpoint, payload)
            print(f"[{index}/{len(filenames)}] {filename}", flush=True)
    return _build_payload(settings, repair_retries, filenames, results, failures)


def _build_payload(
    settings: Any,
    repair_retries: int,
    filenames: list[str],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "trial_config": {
            "model": settings.llm_model,
            "temperature": 0.0,
            "repair_retries": repair_retries,
            "schema": "B2 StructuredFieldRecord",
        },
        "summary": {
            "total_files": len(filenames),
            "success_count": len(results),
            "fail_count": len(failures),
            "total_tokens": sum(int(item.get("tokens") or 0) for item in results),
        },
        "results": results,
            "failures": failures,
    }


def _load_checkpoint(
    checkpoint: Path | None,
    settings: Any,
    repair_retries: int,
) -> dict[str, Any]:
    if checkpoint is None or not checkpoint.exists():
        return _build_payload(settings, repair_retries, [], [], [])
    try:
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        if not isinstance(payload.get("results"), list) or not isinstance(payload.get("failures"), list):
            raise ValueError("缺少 results 或 failures 数组")
        return payload
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"B2 检查点无效，拒绝覆盖：{checkpoint}") from exc


def _write_checkpoint(checkpoint: Path | None, payload: dict[str, Any]) -> None:
    if checkpoint is None:
        return
    if not checkpoint.parent.is_dir():
        raise RuntimeError(f"B2 检查点目录不可用：{checkpoint.parent}")
    temporary = checkpoint.with_suffix(checkpoint.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(checkpoint)


def ensure_checkpoint_writable(checkpoint: Path | str) -> None:
    """在任何 API 调用前验证检查点目录可写，避免成功结果丢失。"""

    path = Path(checkpoint)
    if not path.parent.is_dir():
        raise RuntimeError(f"B2 输出目录不存在：{path.parent}")
    probe = path.parent / ".b2_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise RuntimeError(f"B2 输出目录不可写：{path.parent}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="B2 结构化输出试点（会调用 API）")
    parser.add_argument("--input-dir", type=Path, default=Path("literature/optical-communications/evaluation"))
    parser.add_argument("--manifest", type=Path, default=Path("eval/b2_pilot_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("eval/predictions/b2-structured-pilot/predictions.json"))
    parser.add_argument("--repair-retries", type=int, default=2)
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="重试检查点中的失败论文；已有成功结果仍会跳过",
    )
    parser.add_argument("--confirm-cost", action="store_true", help="确认会对 10 篇试点论文调用 DeepSeek")
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("此命令会调用 DeepSeek；确认后加 --confirm-cost")
    if args.repair_retries < 0:
        parser.error("--repair-retries 不能小于 0")
    ensure_checkpoint_writable(args.output)
    payload = run_structured_trial(
        args.input_dir,
        load_manifest(args.manifest),
        repair_retries=args.repair_retries,
        checkpoint_path=args.output,
        retry_failures=args.retry_failures,
    )
    print(f"B2 预测已保存：{args.output.resolve()}")


if __name__ == "__main__":
    main()
