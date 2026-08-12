"""M4 批量调度：串联文档解析与结构化抽取。"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings
from app.extractor import Extractor
from app.llm import LLMClient
from app.models import (
    BatchFileResult,
    BatchProgressStatus,
    BatchResult,
    ExtractionFailure,
    ExtractionResult,
    ExtractionStage,
    ParsedDoc,
)
from app.parser import DocumentParserError, SUPPORTED_SUFFIXES, parse_document


ProgressCallback = Callable[[int, int, str, str], None]
DocumentParser = Callable[[Path], ParsedDoc]


class TextExtractor(Protocol):
    """M4 依赖的最小抽取接口，便于测试时注入本地假对象。"""

    def extract(self, text: str) -> ExtractionResult: ...


def discover_documents(input_dir: Path | str) -> list[Path]:
    """读取输入目录中的全部 PDF / DOCX，并按文件名稳定排序。"""

    directory = Path(input_dir)
    if not directory.exists():
        raise FileNotFoundError(f"输入文件夹不存在：{directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"INPUT_DIR 不是文件夹：{directory}")
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: path.name.casefold(),
    )


def run_batch(
    files: Iterable[Path | str],
    on_progress: ProgressCallback | None = None,
    *,
    concurrency: int | None = None,
    settings: Settings | None = None,
    parser: DocumentParser = parse_document,
    extractor: TextExtractor | None = None,
) -> BatchResult:
    """解析并抽取一批文件，同时报告完成进度。

    ``on_progress`` 在每份文件完成时由调度主线程调用，参数依次为：已完成数、
    总数、文件名和 ``success``/``failed``。返回明细保持输入顺序，即使并发任务
    的实际完成顺序不同，也方便数据库与界面稳定展示。
    """

    file_paths = [Path(file) for file in files]
    active_settings = settings
    if active_settings is None and (concurrency is None or extractor is None):
        active_settings = get_settings()

    if concurrency is None:
        if active_settings is None:
            raise AssertionError("默认并发数需要项目配置")
        worker_count = active_settings.batch_concurrency
    else:
        worker_count = concurrency
    if worker_count < 1:
        raise ValueError("concurrency 必须大于等于 1；设为 1 可关闭并发")

    if extractor is not None:
        return _run_with_dependencies(
            file_paths,
            parser,
            extractor,
            worker_count,
            on_progress,
        )

    if active_settings is None:
        raise AssertionError("真实抽取器需要项目配置")
    with LLMClient(settings=active_settings) as llm_client:
        real_extractor = Extractor(active_settings, llm_client)
        return _run_with_dependencies(
            file_paths,
            parser,
            real_extractor,
            worker_count,
            on_progress,
        )


def _run_with_dependencies(
    files: list[Path],
    parser: DocumentParser,
    extractor: TextExtractor,
    concurrency: int,
    on_progress: ProgressCallback | None,
) -> BatchResult:
    started_at = time.perf_counter()
    ordered_results: list[BatchFileResult | None] = [None] * len(files)

    with ThreadPoolExecutor(
        max_workers=concurrency,
        thread_name_prefix="paper-extractor",
    ) as executor:
        future_indexes: dict[Future[BatchFileResult], int] = {
            executor.submit(_process_one, path, parser, extractor): index
            for index, path in enumerate(files)
        }

        completed = 0
        for future in as_completed(future_indexes):
            index = future_indexes[future]
            try:
                result = future.result()
            except Exception as exc:  # worker 最外层保险，确保整批仍能完成。
                result = _failed_file(
                    files[index],
                    ExtractionStage.PIPELINE,
                    exc,
                    time.perf_counter(),
                )
            ordered_results[index] = result
            completed += 1
            if on_progress is not None:
                status = (
                    BatchProgressStatus.SUCCESS
                    if result.success
                    else BatchProgressStatus.FAILED
                )
                on_progress(
                    completed,
                    len(files),
                    result.filename,
                    status.value,
                )

    results = [result for result in ordered_results if result is not None]
    success_count = sum(item.success for item in results)
    return BatchResult(
        total_files=len(results),
        success_count=success_count,
        fail_count=len(results) - success_count,
        total_tokens=sum(item.total_tokens for item in results),
        duration_ms=_elapsed_ms(started_at),
        files=results,
    )


def _process_one(
    path: Path,
    parser: DocumentParser,
    extractor: TextExtractor,
) -> BatchFileResult:
    started_at = time.perf_counter()
    try:
        parsed_doc = parser(path)
    except DocumentParserError as exc:
        return _failed_file(path, ExtractionStage.PARSE, exc, started_at)
    except Exception as exc:  # 最后的文件级安全网，避免一份输入中断整批。
        return _failed_file(path, ExtractionStage.PIPELINE, exc, started_at)

    try:
        extraction = extractor.extract(parsed_doc.text)
    except Exception as exc:  # 自定义抽取器或未来代码缺陷也隔离到当前文件。
        return _failed_file(path, ExtractionStage.PIPELINE, exc, started_at)

    return BatchFileResult(
        path=path,
        filename=path.name,
        success=extraction.success,
        record=extraction.record,
        failure=extraction.failure,
        retry_count=extraction.retry_count,
        total_tokens=extraction.total_tokens,
        duration_ms=_elapsed_ms(started_at),
        attempts=extraction.attempts,
    )


def _failed_file(
    path: Path,
    stage: ExtractionStage,
    error: Exception,
    started_at: float,
) -> BatchFileResult:
    message = str(error).strip() or type(error).__name__
    return BatchFileResult(
        path=path,
        filename=path.name or str(path),
        success=False,
        failure=ExtractionFailure(
            stage=stage,
            error_type=type(error).__name__,
            error_msg=message[:1500],
        ),
        duration_ms=_elapsed_ms(started_at),
    )


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
