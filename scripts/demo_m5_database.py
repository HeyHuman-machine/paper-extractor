"""VS Code 可直接运行的 M5 演示：保存并重新查询临时 SQLite 数据库。"""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import get_failures, get_results, get_task, save_batch  # noqa: E402
from app.models import (  # noqa: E402
    BatchFileResult,
    BatchResult,
    DocumentType,
    ExtractionFailure,
    ExtractionStage,
    PaperRecord,
)


def success(filename: str, index: int) -> BatchFileResult:
    return BatchFileResult(
        path=Path(filename),
        filename=filename,
        success=True,
        record=PaperRecord(
            title=f"演示论文 {index}",
            authors=[f"Author {index}", "共同作者"],
            year=2024 + index,
            venue="DemoConf",
            doc_type=DocumentType.CONFERENCE_PAPER,
            problem="演示 SQLite 持久化",
            method_name="PaperExtractor",
            experimental_conditions=["16-Gbaud 16QAM", "20 km SSMF"],
            main_results=[f"Metric {90 + index}%"],
            limitations=None,
            summary="这是一条不调用 DeepSeek 的 M5 演示数据。",
        ),
        total_tokens=100 + index,
        duration_ms=40 + index,
    )


def failure(filename: str) -> BatchFileResult:
    return BatchFileResult(
        path=Path(filename),
        filename=filename,
        success=False,
        failure=ExtractionFailure(
            stage=ExtractionStage.PARSE,
            error_type="CorruptedDocumentError",
            error_msg="演示：文件损坏",
        ),
        duration_ms=5,
    )


def main() -> None:
    files = [success("paper-1.pdf", 1), success("paper-2.pdf", 2), failure("broken.pdf")]
    batch = BatchResult(
        total_files=3,
        success_count=2,
        fail_count=1,
        total_tokens=sum(item.total_tokens for item in files),
        duration_ms=120,
        files=files,
    )

    demo_dir = Path(tempfile.mkdtemp(prefix="paper-extractor-m5-"))
    db_path = demo_dir / "demo.db"
    task_id = save_batch(batch, db_path)

    # 三个查询函数都会重新打开数据库，证明数据不是只留在 Python 内存中。
    task = get_task(task_id, db_path)
    results = get_results(task_id, db_path)
    failures = get_failures(task_id, db_path)

    print("M5 SQLite demo (no DeepSeek API call)")
    print(f"database: {db_path}")
    print(f"task_id: {task_id}")
    print(
        f"summary: total={task['total_files']}, "
        f"success={task['success_count']}, failed={task['fail_count']}"
    )
    print(f"results rows: {len(results)}")
    for row in results:
        print(f"[RESULT] {row['filename']} -> {row['title']} / {row['authors']}")
    print(f"failures rows: {len(failures)}")
    for row in failures:
        print(f"[FAIL] {row['filename']} -> {row['stage']} / {row['error_type']}")


if __name__ == "__main__":
    main()
