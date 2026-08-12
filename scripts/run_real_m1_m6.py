"""自动处理 INPUT_DIR 中全部论文的 M1～M6 端到端入口。"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.db import get_failures, get_results, get_task, save_batch  # noqa: E402
from app.exporter import export_excel, export_json  # noqa: E402
from app.pipeline import discover_documents, run_batch  # noqa: E402


def _show_progress(
    current: int,
    total: int,
    filename: str,
    status: str,
) -> None:
    print(f"[{current}/{total}] {status.upper():7} {filename}", flush=True)


def main() -> None:
    settings = get_settings()
    files = discover_documents(settings.input_dir)
    if not files:
        raise FileNotFoundError(
            "输入文件夹中没有可处理的 PDF / DOCX："
            f"{settings.input_dir}"
        )

    print(f"输入文件夹：{settings.input_dir}", flush=True)
    print(f"自动发现 {len(files)} 份论文：", flush=True)
    for path in files:
        print(f"- {path.name}", flush=True)
    print("开始执行 M1～M6（会调用 DeepSeek）", flush=True)
    batch = run_batch(files, on_progress=_show_progress, settings=settings)

    output_dir = settings.output_dir
    db_path = settings.db_path
    task_id = save_batch(batch, db_path)
    excel_path = export_excel(
        task_id,
        output_dir / "论文对比表.xlsx",
        db_path=db_path,
    )
    json_path = export_json(
        task_id,
        output_dir / "论文完整数据.json",
        db_path=db_path,
    )

    task = get_task(task_id, db_path)
    results = get_results(task_id, db_path)
    failures = get_failures(task_id, db_path)
    print("\n真实流程完成", flush=True)
    print(f"task_id: {task_id}", flush=True)
    print(
        f"summary: total={task['total_files']}, "
        f"success={task['success_count']}, failed={task['fail_count']}, "
        f"tokens={task['total_tokens']}, duration_ms={task['duration_ms']}",
        flush=True,
    )
    for row in results:
        print(f"[RESULT] {row['filename']} -> {row['title']}", flush=True)
    for row in failures:
        print(
            f"[FAIL] {row['filename']} -> {row['stage']} / "
            f"{row['error_type']}: {row['error_msg']}",
            flush=True,
        )
    print(f"Excel: {excel_path}", flush=True)
    print(f"JSON: {json_path}", flush=True)


if __name__ == "__main__":
    main()
