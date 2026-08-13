"""M7 FastAPI 接口测试：不访问真实 DeepSeek。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import api as api_module
from app.config import Settings
from app.models import (
    BatchFileResult,
    BatchResult,
    DocumentType,
    ExtractionFailure,
    ExtractionStage,
    PaperRecord,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": "https://example.invalid/v1",
            "LLM_MODEL": "test-model",
            "LLM_API_KEY": "test-key-not-real",
            "INPUT_DIR": str(tmp_path / "input"),
            "OUTPUT_DIR": str(tmp_path / "output"),
            "DB_PATH": str(tmp_path / "api.db"),
            "LOG_PATH": str(tmp_path / "app.log"),
        }
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> TestClient:
    monkeypatch.setattr(api_module, "get_settings", lambda: settings)
    return TestClient(api_module.app)


def _record(title: str = "光通信测试论文") -> PaperRecord:
    return PaperRecord(
        title=title,
        authors=["张三", "Alice"],
        year=2025,
        venue="Optics Test",
        doc_type=DocumentType.JOURNAL_ARTICLE,
        problem="验证 FastAPI 上传与查询流程",
        method_name="Single-PD receiver",
        experimental_conditions=["16-Gbaud QPSK", "20 km SSMF"],
        main_results=["BER below HD-FEC threshold"],
        limitations=None,
        summary="用于 M7 接口测试的结构化论文记录。",
    )


def _success_batch(path: Path) -> BatchResult:
    item = BatchFileResult(
        path=path,
        filename=path.name,
        success=True,
        record=_record(),
        total_tokens=120,
        duration_ms=35,
    )
    return BatchResult(
        total_files=1,
        success_count=1,
        fail_count=0,
        total_tokens=120,
        duration_ms=40,
        files=[item],
    )


def _failed_batch(filename: str = "broken.pdf") -> BatchResult:
    item = BatchFileResult(
        path=Path(filename),
        filename=filename,
        success=False,
        failure=ExtractionFailure(
            stage=ExtractionStage.PARSE,
            error_type="CorruptedDocumentError",
            error_msg="文件损坏",
        ),
        duration_ms=5,
    )
    return BatchResult(
        total_files=1,
        success_count=0,
        fail_count=1,
        total_tokens=0,
        duration_ms=5,
        files=[item],
    )


def test_health_docs_and_openapi_are_available(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/tasks" in paths
    assert "/api/tasks/{task_id}/export" in paths


def test_openapi_marks_each_upload_as_binary(client: TestClient) -> None:
    """Swagger 必须渲染文件选择器，不能把 PDF 字节显示为字符串乱码。"""

    schema = client.get("/openapi.json").json()
    body_schema = schema["components"]["schemas"][
        "Body_create_task_api_tasks_post"
    ]

    assert body_schema["properties"]["files"]["type"] == "array"
    assert body_schema["properties"]["files"]["items"] == {
        "type": "string",
        "format": "binary",
    }


def test_upload_runs_batch_saves_task_and_returns_m3_schema(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_run_batch(files: list[Path], *, settings: Settings) -> BatchResult:
        observed["exists_during_run"] = files[0].exists()
        observed["content"] = files[0].read_bytes()
        return _success_batch(files[0])

    monkeypatch.setattr(api_module, "run_batch", fake_run_batch)
    response = client.post(
        "/api/tasks",
        files=[("files", ("paper.pdf", b"fake-pdf", "application/pdf"))],
    )

    assert response.status_code == 201
    payload = response.json()
    assert observed == {"exists_during_run": True, "content": b"fake-pdf"}
    assert payload["task"]["id"] == 1
    assert payload["task"]["success_count"] == 1
    assert payload["results"][0]["title"] == "光通信测试论文"
    assert payload["results"][0]["experimental_conditions"] == [
        "16-Gbaud QPSK",
        "20 km SSMF",
    ]
    assert "raw_llm_output" not in payload["results"][0]


def test_task_list_detail_and_failures_share_task_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_module,
        "run_batch",
        lambda files, *, settings: _failed_batch(files[0].name),
    )
    created = client.post(
        "/api/tasks",
        files=[("files", ("broken.pdf", b"broken", "application/pdf"))],
    ).json()
    task_id = created["task"]["id"]

    listed = client.get("/api/tasks?limit=10&offset=0").json()
    detail = client.get(f"/api/tasks/{task_id}").json()
    failures = client.get(f"/api/tasks/{task_id}/failures").json()

    assert listed["total"] == 1
    assert listed["items"][0]["id"] == task_id
    assert detail["results"] == []
    assert failures["task_id"] == task_id
    assert failures["failures"][0]["error_type"] == "CorruptedDocumentError"


def test_export_downloads_excel_and_json(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_module,
        "run_batch",
        lambda files, *, settings: _success_batch(files[0]),
    )
    task_id = client.post(
        "/api/tasks",
        files=[("files", ("paper.pdf", b"pdf", "application/pdf"))],
    ).json()["task"]["id"]

    excel = client.get(f"/api/tasks/{task_id}/export?format=xlsx")
    json_file = client.get(f"/api/tasks/{task_id}/export?format=json")

    assert excel.status_code == 200
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert excel.content.startswith(b"PK")
    assert json_file.status_code == 200
    assert json_file.json()["task"]["id"] == task_id


def test_errors_use_one_structured_shape(client: TestClient) -> None:
    missing = client.get("/api/tasks/999")
    invalid_format = client.get("/api/tasks/999/export?format=csv")
    unsupported = client.post(
        "/api/tasks",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["type"] == "TaskNotFoundError"
    assert invalid_format.status_code == 422
    assert invalid_format.json()["error"]["type"] == "RequestValidationError"
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["type"] == "HTTPException"


def test_text_form_value_returns_422_instead_of_hiding_error_as_500(
    client: TestClient,
) -> None:
    """旧 Swagger 若提交 files=string，也必须暴露清楚的参数错误。"""

    response = client.post("/api/tasks", data={"files": "string"})

    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["type"] == "RequestValidationError"
    assert payload["details"][0]["location"] == ["body", "files", 0]
    assert "UploadFile" in payload["details"][0]["message"]
