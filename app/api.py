"""M7 FastAPI：把 M1～M6 流程封装成可调用的 HTTP 接口。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request

from app.config import ConfigurationError, get_settings
from app.db import count_tasks, get_failures, get_results, get_task, list_tasks, save_batch
from app.exporter import TaskNotFoundError, export_excel, export_json
from app.models import PaperRecord
from app.parser import SUPPORTED_SUFFIXES
from app.pipeline import run_batch


class TaskSummary(BaseModel):
    """一批论文处理任务的状态与运行指标。"""

    id: int
    created_at: str
    finished_at: str | None
    status: Literal["running", "completed", "failed"]
    total_files: int
    success_count: int
    fail_count: int
    total_tokens: int
    duration_ms: int


class PaperResultResponse(PaperRecord):
    """复用 M3 的 11 字段模型，并补充数据库与运行信息。"""

    id: int
    task_id: int
    filename: str
    retry_count: int
    tokens: int
    latency_ms: int


class FailureResponse(BaseModel):
    id: int
    task_id: int
    filename: str
    stage: str
    error_type: str
    error_msg: str
    raw_output: str | None
    retry_count: int
    created_at: str


class TaskDetailResponse(BaseModel):
    task: TaskSummary
    results: list[PaperResultResponse]


class FailureListResponse(BaseModel):
    task_id: int
    failures: list[FailureResponse]


class TaskListResponse(BaseModel):
    items: list[TaskSummary]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorBody(BaseModel):
    type: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def _error_response(
    status_code: int,
    error_type: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            ErrorResponse(
                error=ErrorBody(type=error_type, message=message, details=details)
            )
        ),
    )


def _task_or_404(task_id: int, db_path: Path) -> dict[str, Any]:
    task = get_task(task_id, db_path)
    if task is None:
        raise TaskNotFoundError(f"任务不存在：{task_id}")
    return task


def _public_result(row: dict[str, Any]) -> dict[str, Any]:
    """API 不返回仅用于内部诊断的模型原始输出。"""

    return {key: value for key, value in row.items() if key != "raw_llm_output"}


def create_app() -> FastAPI:
    app = FastAPI(
        title="PaperExtractor API",
        version="0.1.0",
        description="上传论文、查看结构化抽取结果并导出 Excel / JSON。",
    )

    @app.middleware("http")
    async def unexpected_error_middleware(request: Request, call_next: Any):
        """把未预料异常统一为结构化响应，避免向调用方泄露堆栈。"""

        try:
            return await call_next(request)
        except TaskNotFoundError as exc:
            return _error_response(404, type(exc).__name__, str(exc))
        except ConfigurationError as exc:
            return _error_response(500, type(exc).__name__, str(exc))
        except Exception:
            return _error_response(500, "InternalServerError", "服务器内部错误")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        return _error_response(exc.status_code, "HTTPException", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(422, "RequestValidationError", "请求参数校验失败", exc.errors())

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post(
        "/api/tasks",
        response_model=TaskDetailResponse,
        status_code=201,
        tags=["tasks"],
    )
    def create_task(
        files: Annotated[list[UploadFile], File(description="PDF / DOCX 文件，可多选")],
    ) -> TaskDetailResponse:
        if not files:
            raise HTTPException(status_code=400, detail="至少上传一个文件")
        settings = get_settings()
        with tempfile.TemporaryDirectory(prefix="paper-extractor-api-") as temp_dir:
            saved_paths: list[Path] = []
            used_names: set[str] = set()
            for upload in files:
                safe_name = Path(upload.filename or "").name
                suffix = Path(safe_name).suffix.lower()
                if not safe_name or suffix not in SUPPORTED_SUFFIXES:
                    allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
                    raise HTTPException(
                        status_code=400,
                        detail=f"仅支持 {allowed} 文件：{safe_name or '未命名文件'}",
                    )
                safe_name = _unique_name(safe_name, used_names)
                destination = Path(temp_dir) / safe_name
                with destination.open("wb") as output:
                    shutil.copyfileobj(upload.file, output)
                upload.file.close()
                saved_paths.append(destination)

            batch = run_batch(saved_paths, settings=settings)
            task_id = save_batch(batch, settings.db_path)

        task = _task_or_404(task_id, settings.db_path)
        results = [_public_result(row) for row in get_results(task_id, settings.db_path)]
        return TaskDetailResponse(task=task, results=results)

    @app.get("/api/tasks", response_model=TaskListResponse, tags=["tasks"])
    def read_tasks(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> TaskListResponse:
        settings = get_settings()
        return TaskListResponse(
            items=list_tasks(limit=limit, offset=offset, db_path=settings.db_path),
            total=count_tasks(settings.db_path),
            limit=limit,
            offset=offset,
        )

    @app.get("/api/tasks/{task_id}", response_model=TaskDetailResponse, tags=["tasks"])
    def read_task(task_id: int) -> TaskDetailResponse:
        settings = get_settings()
        task = _task_or_404(task_id, settings.db_path)
        results = [_public_result(row) for row in get_results(task_id, settings.db_path)]
        return TaskDetailResponse(task=task, results=results)

    @app.get(
        "/api/tasks/{task_id}/failures",
        response_model=FailureListResponse,
        tags=["tasks"],
    )
    def read_failures(task_id: int) -> FailureListResponse:
        settings = get_settings()
        _task_or_404(task_id, settings.db_path)
        return FailureListResponse(
            task_id=task_id,
            failures=get_failures(task_id, settings.db_path),
        )

    @app.get("/api/tasks/{task_id}/export", tags=["export"])
    def download_export(
        task_id: int,
        format: Annotated[Literal["xlsx", "json"], Query()] = "xlsx",
    ) -> FileResponse:
        settings = get_settings()
        _task_or_404(task_id, settings.db_path)
        export_dir = settings.output_dir / "api-exports"
        if format == "xlsx":
            path = export_excel(
                task_id,
                export_dir / f"task-{task_id}.xlsx",
                db_path=settings.db_path,
            )
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            path = export_json(
                task_id,
                export_dir / f"task-{task_id}.json",
                db_path=settings.db_path,
            )
            media_type = "application/json"
        return FileResponse(path, media_type=media_type, filename=path.name)

    return app


def _unique_name(filename: str, used_names: set[str]) -> str:
    """同一请求上传同名文件时保留两份，并确保路径不会越出临时目录。"""

    candidate = filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem}-{index}{suffix}"
        index += 1
    used_names.add(candidate.casefold())
    return candidate


app = create_app()
