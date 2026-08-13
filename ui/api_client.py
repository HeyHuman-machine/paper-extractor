"""供 Streamlit 使用的 M7 HTTP 客户端。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

import httpx


class APIClientError(RuntimeError):
    """M7 不可用或返回错误响应。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PaperExtractorAPI:
    """用普通 HTTP 调用 M7，避免 UI 重复业务逻辑。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 600,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def health(self) -> bool:
        try:
            with self._client(timeout=3) as client:
                response = client.get(f"{self.base_url}/health")
            return response.status_code == 200 and response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    def create_task(self, uploaded_files: list[Any]) -> dict[str, Any]:
        files: list[tuple[str, tuple[str, BinaryIO, str]]] = []
        for uploaded in uploaded_files:
            uploaded.seek(0)
            media_type = getattr(uploaded, "type", None) or "application/octet-stream"
            files.append(("files", (uploaded.name, uploaded, media_type)))
        return self._request("POST", "/api/tasks", files=files)

    def list_tasks(self, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return self._request("GET", "/api/tasks", params={"limit": limit, "offset": offset})

    def get_task(self, task_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/tasks/{task_id}")

    def get_failures(self, task_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/tasks/{task_id}/failures")

    def download_export(self, task_id: int, format: str) -> tuple[bytes, str]:
        response = self._raw_request(
            "GET",
            f"/api/tasks/{task_id}/export",
            params={"format": format},
        )
        disposition = response.headers.get("content-disposition", "")
        filename = f"task-{task_id}.{format}"
        if "filename=" in disposition:
            filename = disposition.split("filename=", 1)[1].strip('"')
        return response.content, filename

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._raw_request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise APIClientError("M7 返回了无法解析的 JSON") from exc

    def _raw_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            with self._client(timeout=self.timeout) as client:
                response = client.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise APIClientError(f"无法连接 M7：{exc}") from exc
        if response.is_error:
            raise APIClientError(
                self._error_message(response),
                status_code=response.status_code,
            )
        return response

    def _client(self, *, timeout: float) -> httpx.Client:
        return httpx.Client(
            trust_env=False,
            timeout=timeout,
            transport=self.transport,
        )

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return payload.get("error", {}).get("message") or response.text
        except ValueError:
            return response.text or f"HTTP {response.status_code}"
