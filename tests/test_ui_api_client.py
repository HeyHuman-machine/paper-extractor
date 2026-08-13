"""M8 到 M7 的 HTTP 客户端测试。"""

from __future__ import annotations

from io import BytesIO

import httpx
import pytest

from ui.api_client import APIClientError, PaperExtractorAPI


class Uploaded(BytesIO):
    name = "论文.pdf"
    type = "application/pdf"


def test_health_returns_false_when_api_is_unavailable() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = PaperExtractorAPI(transport=httpx.MockTransport(unavailable))
    assert client.health() is False


def test_create_task_sends_real_multipart_file() -> None:
    observed: dict[str, object] = {}

    def fake_request(request: httpx.Request) -> httpx.Response:
        body = request.read()
        observed["method"] = request.method
        observed["url"] = str(request.url)
        observed["has_filename"] = 'filename="论文.pdf"'.encode() in body
        observed["has_content"] = b"%PDF-fake" in body
        return httpx.Response(201, json={"task": {"id": 4}, "results": []})

    payload = PaperExtractorAPI(
        transport=httpx.MockTransport(fake_request)
    ).create_task([Uploaded(b"%PDF-fake")])

    assert payload["task"]["id"] == 4
    assert observed == {
        "method": "POST",
        "url": "http://127.0.0.1:8000/api/tasks",
        "has_filename": True,
        "has_content": True,
    }


def test_structured_api_error_becomes_readable_exception() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            404,
            json={"error": {"message": "任务不存在：99"}},
        )
    )

    with pytest.raises(APIClientError, match="任务不存在：99") as error:
        PaperExtractorAPI(transport=transport).get_task(99)

    assert error.value.status_code == 404


def test_download_export_returns_bytes_and_filename() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=b"PK-xlsx",
            headers={"content-disposition": 'attachment; filename="task-3.xlsx"'},
        )
    )

    content, filename = PaperExtractorAPI(transport=transport).download_export(3, "xlsx")

    assert content == b"PK-xlsx"
    assert filename == "task-3.xlsx"
