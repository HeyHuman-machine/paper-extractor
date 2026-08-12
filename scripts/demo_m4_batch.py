"""VS Code 可直接运行的 M4 演示：10 个文件、8 成功、2 失败。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import (  # noqa: E402
    DocumentType,
    ExtractionFailure,
    ExtractionResult,
    ExtractionStage,
    PaperRecord,
    ParsedDoc,
)
from app.parser import CorruptedDocumentError  # noqa: E402
from app.pipeline import run_batch  # noqa: E402


class DemoExtractor:
    """本地模拟 M3，展示调度行为而不消耗 API 余额。"""

    def extract(self, text: str) -> ExtractionResult:
        time.sleep(0.05)
        if "bad-json" in text:
            return ExtractionResult(
                success=False,
                failure=ExtractionFailure(
                    stage=ExtractionStage.JSON_PARSE,
                    error_type="JSONExtractionError",
                    error_msg="演示：两次修正后仍没有可解析 JSON",
                ),
                retry_count=2,
                total_tokens=90,
                total_latency_ms=50,
            )
        filename = text.removeprefix("论文正文：")
        return ExtractionResult(
            success=True,
            record=PaperRecord(
                title=f"演示论文 · {filename}",
                authors=["Demo Author"],
                year=2026,
                venue=None,
                doc_type=DocumentType.OTHER,
                problem="演示批量调度",
                method_name=None,
                experimental_conditions=["16-Gbaud 16QAM", "20 km SSMF"],
                main_results=["该文件成功完成解析与抽取"],
                limitations=None,
                summary="这是不访问 DeepSeek 的 M4 本地演示结果。",
            ),
            total_tokens=100,
            total_latency_ms=50,
        )


def demo_parser(path: Path) -> ParsedDoc:
    time.sleep(0.02)
    if path.name == "broken.pdf":
        raise CorruptedDocumentError("演示：PDF 文件损坏")
    text = f"论文正文：{path.name}"
    return ParsedDoc(
        path=path,
        file_name=path.name,
        file_type="pdf",
        page_count=1,
        text=text,
        pages=[text],
    )


def show_progress(current: int, total: int, filename: str, status: str) -> None:
    label = "OK" if status == "success" else "FAIL"
    print(f"[{current:02d}/{total:02d}] [{label:<4}] {filename:<14} {status}")


def main() -> None:
    files = [Path(f"paper-{index}.pdf") for index in range(1, 9)]
    files.extend([Path("broken.pdf"), Path("bad-json.pdf")])

    print("M4 批量调度演示：默认 3 并发，本演示不会调用 DeepSeek。\n")
    result = run_batch(
        files,
        on_progress=show_progress,
        concurrency=3,
        parser=demo_parser,
        extractor=DemoExtractor(),
    )

    print("\n批次完成")
    print(f"总数：{result.total_files}")
    print(f"成功：{result.success_count}")
    print(f"失败：{result.fail_count}")
    print(f"Token：{result.total_tokens}")
    print(f"耗时：{result.duration_ms} ms")
    for item in result.files:
        if item.failure:
            print(
                f"- {item.filename}: {item.failure.stage.value} / "
                f"{item.failure.error_msg}"
            )


if __name__ == "__main__":
    main()
