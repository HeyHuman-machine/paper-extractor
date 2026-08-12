"""M4 批量调度测试：不访问真实文件解析器或 DeepSeek。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app import pipeline as pipeline_module
from app.models import (
    DocumentType,
    ExtractionFailure,
    ExtractionResult,
    ExtractionStage,
    PaperRecord,
    ParsedDoc,
)
from app.parser import CorruptedDocumentError
from app.pipeline import discover_documents, run_batch


def test_discover_documents_reads_supported_files_and_sorts_names(
    tmp_path: Path,
) -> None:
    (tmp_path / "B.docx").write_bytes(b"docx")
    (tmp_path / "a.PDF").write_bytes(b"pdf")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "inside.pdf").write_bytes(b"pdf")

    files = discover_documents(tmp_path)

    assert [path.name for path in files] == ["a.PDF", "B.docx"]


def test_discover_documents_rejects_missing_or_non_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="输入文件夹不存在"):
        discover_documents(tmp_path / "missing")

    file_path = tmp_path / "paper.pdf"
    file_path.write_bytes(b"pdf")
    with pytest.raises(NotADirectoryError, match="INPUT_DIR"):
        discover_documents(file_path)


def paper_record(title: str) -> PaperRecord:
    return PaperRecord(
        title=title,
        authors=["Test Author"],
        year=2026,
        venue=None,
        doc_type=DocumentType.OTHER,
        problem="test problem",
        method_name=None,
        experimental_conditions=[],
        main_results=[],
        limitations=None,
        summary="test summary",
    )


def parsed(path: Path, text: str | None = None) -> ParsedDoc:
    content = text or f"content:{path.name}"
    return ParsedDoc(
        path=path,
        file_name=path.name,
        file_type="pdf",
        page_count=1,
        text=content,
        pages=[content],
    )


class FakeExtractor:
    def extract(self, text: str) -> ExtractionResult:
        return ExtractionResult(
            success=True,
            record=paper_record(text.removeprefix("content:")),
            total_tokens=10,
            total_latency_ms=2,
        )


def test_batch_collects_successes_and_reports_progress() -> None:
    progress: list[tuple[int, int, str, str]] = []
    files = [Path("a.pdf"), Path("b.pdf"), Path("c.pdf")]

    result = run_batch(
        files,
        on_progress=lambda *args: progress.append(args),
        concurrency=2,
        parser=parsed,
        extractor=FakeExtractor(),
    )

    assert result.total_files == 3
    assert result.success_count == 3
    assert result.fail_count == 0
    assert result.total_tokens == 30
    assert [item.filename for item in result.files] == [
        "a.pdf",
        "b.pdf",
        "c.pdf",
    ]
    assert [item.record.title for item in result.files if item.record] == [
        "a.pdf",
        "b.pdf",
        "c.pdf",
    ]
    assert [item[0] for item in progress] == [1, 2, 3]
    assert all(item[1] == 3 and item[3] == "success" for item in progress)


def test_parse_and_extract_failures_do_not_stop_other_files() -> None:
    files = [Path("good-a.pdf"), Path("broken.pdf"), Path("bad-json.pdf")]

    def fake_parser(path: Path) -> ParsedDoc:
        if path.name == "broken.pdf":
            raise CorruptedDocumentError("document is broken")
        return parsed(path)

    class SometimesFailingExtractor:
        def extract(self, text: str) -> ExtractionResult:
            if text.endswith("bad-json.pdf"):
                return ExtractionResult(
                    success=False,
                    failure=ExtractionFailure(
                        stage=ExtractionStage.JSON_PARSE,
                        error_type="JSONExtractionError",
                        error_msg="not json",
                    ),
                    retry_count=2,
                    total_tokens=25,
                    total_latency_ms=5,
                )
            return FakeExtractor().extract(text)

    result = run_batch(
        files,
        concurrency=3,
        parser=fake_parser,
        extractor=SometimesFailingExtractor(),
    )

    assert result.success_count == 1
    assert result.fail_count == 2
    assert result.files[0].success is True
    assert result.files[1].failure is not None
    assert result.files[1].failure.stage == ExtractionStage.PARSE
    assert result.files[2].failure is not None
    assert result.files[2].failure.stage == ExtractionStage.JSON_PARSE
    assert result.files[2].retry_count == 2


def test_unexpected_worker_error_is_isolated_as_pipeline_failure() -> None:
    def exploding_parser(path: Path) -> ParsedDoc:
        if path.name == "bug.pdf":
            raise RuntimeError("unexpected bug")
        return parsed(path)

    result = run_batch(
        [Path("bug.pdf"), Path("good.pdf")],
        concurrency=2,
        parser=exploding_parser,
        extractor=FakeExtractor(),
    )

    assert result.fail_count == 1
    assert result.success_count == 1
    assert result.files[0].failure is not None
    assert result.files[0].failure.stage == ExtractionStage.PIPELINE
    assert result.files[0].failure.error_type == "RuntimeError"


def test_malformed_extractor_result_is_isolated_by_worker_boundary() -> None:
    class BrokenExtractor:
        def extract(self, text: str) -> ExtractionResult:
            return None  # type: ignore[return-value]

    result = run_batch(
        [Path("malformed.pdf"), Path("another.pdf")],
        concurrency=2,
        parser=parsed,
        extractor=BrokenExtractor(),
    )

    assert result.total_files == 2
    assert result.fail_count == 2
    assert all(
        item.failure is not None
        and item.failure.stage == ExtractionStage.PIPELINE
        for item in result.files
    )


def test_concurrency_one_runs_serially() -> None:
    active_workers = 0
    max_active_workers = 0
    lock = threading.Lock()

    def tracked_parser(path: Path) -> ParsedDoc:
        nonlocal active_workers, max_active_workers
        with lock:
            active_workers += 1
            max_active_workers = max(max_active_workers, active_workers)
        time.sleep(0.01)
        with lock:
            active_workers -= 1
        return parsed(path)

    result = run_batch(
        [Path(f"{index}.pdf") for index in range(4)],
        concurrency=1,
        parser=tracked_parser,
        extractor=FakeExtractor(),
    )

    assert result.success_count == 4
    assert max_active_workers == 1


def test_parallel_completion_does_not_change_output_order() -> None:
    delays = {"slow.pdf": 0.03, "fast.pdf": 0.001}
    completed: list[str] = []

    def delayed_parser(path: Path) -> ParsedDoc:
        time.sleep(delays[path.name])
        return parsed(path)

    result = run_batch(
        [Path("slow.pdf"), Path("fast.pdf")],
        on_progress=lambda _current, _total, filename, _status: completed.append(
            filename
        ),
        concurrency=2,
        parser=delayed_parser,
        extractor=FakeExtractor(),
    )

    assert completed == ["fast.pdf", "slow.pdf"]
    assert [item.filename for item in result.files] == ["slow.pdf", "fast.pdf"]


def test_empty_batch_returns_empty_summary() -> None:
    result = run_batch([], concurrency=3, parser=parsed, extractor=FakeExtractor())

    assert result.total_files == 0
    assert result.success_count == 0
    assert result.fail_count == 0
    assert result.files == []


def test_invalid_concurrency_has_clear_error() -> None:
    with pytest.raises(ValueError, match="设为 1 可关闭并发"):
        run_batch([], concurrency=0, parser=parsed, extractor=FakeExtractor())


def test_injected_dependencies_do_not_read_real_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """纯本地测试提供并发数和抽取器后，不应读取真实 API 配置。"""

    monkeypatch.setattr(
        pipeline_module,
        "get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("不应读取 .env")),
    )

    result = run_batch(
        [Path("local.pdf")],
        concurrency=1,
        parser=parsed,
        extractor=FakeExtractor(),
    )

    assert result.success_count == 1
