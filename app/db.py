"""M5 SQLite 持久化：保存并查询 M4 的批次结果。"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models import BatchFileResult, BatchResult


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    total_files INTEGER NOT NULL CHECK (total_files >= 0),
    success_count INTEGER NOT NULL CHECK (success_count >= 0),
    fail_count INTEGER NOT NULL CHECK (fail_count >= 0),
    total_tokens INTEGER NOT NULL CHECK (total_tokens >= 0),
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0)
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    year INTEGER,
    venue TEXT,
    doc_type TEXT NOT NULL,
    problem TEXT NOT NULL,
    method_name TEXT,
    experimental_conditions TEXT NOT NULL,
    main_results TEXT NOT NULL,
    limitations TEXT,
    summary TEXT NOT NULL,
    retry_count INTEGER NOT NULL CHECK (retry_count >= 0),
    tokens INTEGER NOT NULL CHECK (tokens >= 0),
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    raw_llm_output TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    stage TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_msg TEXT NOT NULL,
    raw_output TEXT,
    retry_count INTEGER NOT NULL CHECK (retry_count >= 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_results_task_id ON results(task_id);
CREATE INDEX IF NOT EXISTS idx_failures_task_id ON failures(task_id);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """打开数据库并启用行名访问与外键约束。"""

    path = Path(db_path) if db_path is not None else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: Path | str | None = None) -> None:
    """幂等创建表和索引；重复调用不会清空已有数据。"""

    with connect(db_path) as connection:
        _ensure_schema(connection)


def save_batch(
    batch: BatchResult,
    db_path: Path | str | None = None,
) -> int:
    """在一个事务中保存批次总览、成功结果和失败诊断，返回 task_id。"""

    now = _utc_now()
    with connect(db_path) as connection:
        _ensure_schema(connection)
        try:
            cursor = connection.execute(
                """
                INSERT INTO tasks (
                    created_at, finished_at, status, total_files,
                    success_count, fail_count, total_tokens, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    now,
                    "completed",
                    batch.total_files,
                    batch.success_count,
                    batch.fail_count,
                    batch.total_tokens,
                    batch.duration_ms,
                ),
            )
            task_id = int(cursor.lastrowid)

            for item in batch.files:
                if item.success:
                    _insert_result(connection, task_id, item)
                else:
                    _insert_failure(connection, task_id, item, now)
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
            return task_id


def get_task(
    task_id: int,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """按主键查询一条任务总览。"""

    with connect(db_path) as connection:
        _ensure_schema(connection)
        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return dict(row) if row is not None else None


def list_tasks(
    *,
    limit: int = 20,
    offset: int = 0,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """按最新任务优先分页查询任务总览。"""

    if limit < 1:
        raise ValueError("limit 必须大于等于 1")
    if offset < 0:
        raise ValueError("offset 不能小于 0")
    with connect(db_path) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]


def count_tasks(db_path: Path | str | None = None) -> int:
    """返回任务总数，供 API 分页响应计算。"""

    with connect(db_path) as connection:
        _ensure_schema(connection)
        row = connection.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()
    return int(row["count"])


def get_results(
    task_id: int,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """查询任务的成功结果，并把 JSON 字符串恢复为 Python 列表。"""

    with connect(db_path) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            "SELECT * FROM results WHERE task_id = ? ORDER BY id", (task_id,)
        ).fetchall()
    results = [dict(row) for row in rows]
    for result in results:
        for field in ("authors", "experimental_conditions", "main_results"):
            result[field] = json.loads(result[field])
    return results


def get_failures(
    task_id: int,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """查询任务的失败诊断。"""

    with connect(db_path) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            "SELECT * FROM failures WHERE task_id = ? ORDER BY id", (task_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def _insert_result(
    connection: sqlite3.Connection,
    task_id: int,
    item: BatchFileResult,
) -> None:
    record = item.record
    if record is None:
        raise ValueError("成功文件缺少 PaperRecord")
    raw_output = item.attempts[-1].raw_output if item.attempts else None
    connection.execute(
        """
        INSERT INTO results (
            task_id, filename, title, authors, year, venue, doc_type,
            problem, method_name, experimental_conditions, main_results, limitations,
            summary, retry_count, tokens, latency_ms, raw_llm_output
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            item.filename,
            record.title,
            _json_list(record.authors),
            record.year,
            record.venue,
            record.doc_type.value,
            record.problem,
            record.method_name,
            _json_list(record.experimental_conditions),
            _json_list(record.main_results),
            record.limitations,
            record.summary,
            item.retry_count,
            item.total_tokens,
            item.duration_ms,
            raw_output,
        ),
    )


def _insert_failure(
    connection: sqlite3.Connection,
    task_id: int,
    item: BatchFileResult,
    created_at: str,
) -> None:
    failure = item.failure
    if failure is None:
        raise ValueError("失败文件缺少 ExtractionFailure")
    connection.execute(
        """
        INSERT INTO failures (
            task_id, filename, stage, error_type, error_msg,
            raw_output, retry_count, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            item.filename,
            failure.stage.value,
            failure.error_type,
            failure.error_msg,
            failure.raw_llm_output,
            item.retry_count,
            created_at,
        ),
    )


def _json_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _ensure_schema(connection: sqlite3.Connection) -> None:
    """创建新库，并把旧版 datasets 列无损迁移为实验条件列。"""

    connection.executescript(SCHEMA_SQL)
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(results)")
    }
    if "datasets" in columns and "experimental_conditions" not in columns:
        connection.execute(
            "ALTER TABLE results RENAME COLUMN datasets TO experimental_conditions"
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
