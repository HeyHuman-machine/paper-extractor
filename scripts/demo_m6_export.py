"""VS Code 可直接运行的 M6 演示：从 SQLite 任务导出 Excel 和 JSON。"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import save_batch  # noqa: E402
from app.exporter import export_excel, export_json  # noqa: E402
from app.models import (  # noqa: E402
    BatchFileResult,
    BatchResult,
    DocumentType,
    ExtractionFailure,
    ExtractionStage,
    PaperRecord,
)


def _success(filename: str, index: int) -> BatchFileResult:
    return BatchFileResult(
        path=Path(filename),
        filename=filename,
        success=True,
        record=PaperRecord(
            title=f"演示论文 {index}：批量论文信息抽取",
            authors=[f"Author {index}", "共同作者"],
            year=2024 + index,
            venue="DemoConf",
            doc_type=DocumentType.CONFERENCE_PAPER,
            problem="如何把论文文本稳定整理为结构化对比表",
            method_name="PaperExtractor",
            experimental_conditions=[
                "16-Gbaud 16QAM",
                f"{20 * index} km SSMF",
            ],
            main_results=[f"准确率 {90 + index}%", "支持失败诊断"],
            limitations="当前演示使用构造数据，没有调用 DeepSeek。",
            summary="M6 从 SQLite 按 task_id 查询数据，然后同时导出 Excel 和 JSON。",
        ),
        retry_count=index - 1,
        total_tokens=100 + index,
        duration_ms=40 + index,
    )


def _failure(filename: str) -> BatchFileResult:
    return BatchFileResult(
        path=Path(filename),
        filename=filename,
        success=False,
        failure=ExtractionFailure(
            stage=ExtractionStage.PARSE,
            error_type="CorruptedDocumentError",
            error_msg="演示：文件损坏，无法读取文本",
        ),
        duration_ms=5,
    )


def main() -> None:
    files = [_success("paper-1.pdf", 1), _success("paper-2.pdf", 2), _failure("broken.pdf")]
    batch = BatchResult(
        total_files=3,
        success_count=2,
        fail_count=1,
        total_tokens=sum(item.total_tokens for item in files),
        duration_ms=120,
        files=files,
    )

    output_dir = PROJECT_ROOT / "data" / "output" / "m6-demo"
    db_path = output_dir / "demo.db"
    task_id = save_batch(batch, db_path)
    excel_path = export_excel(task_id, output_dir / "论文对比表.xlsx", db_path=db_path)
    json_path = export_json(task_id, output_dir / "完整结构化数据.json", db_path=db_path)

    print("M6 export demo (no DeepSeek API call)")
    print(f"task_id: {task_id}")
    print(f"Excel: {excel_path}")
    print(f"JSON: {json_path}")
    print("Excel sheets: 论文结果 / 失败记录 / 任务概览")


if __name__ == "__main__":
    main()
