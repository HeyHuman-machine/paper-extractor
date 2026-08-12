"""M5 SQLite 持久化测试。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app import db as db_module
from app.db import get_failures, get_results, get_task, init_db, save_batch
from app.models import (
    BatchFileResult,
    BatchResult,
    DocumentType,
    ExtractionAttempt,
    ExtractionFailure,
    ExtractionStage,
    PaperRecord,
)


def successful_file(filename: str = "成功论文.pdf") -> BatchFileResult:
    return BatchFileResult(
        path=Path(filename),
        filename=filename,
        success=True,
        record=PaperRecord(
            title="测试论文",
            authors=["张三", "Alice"],
            year=2025,
            venue="TestConf",
            doc_type=DocumentType.CONFERENCE_PAPER,
            problem="验证 SQLite 持久化",
            method_name="PaperExtractor",
            experimental_conditions=["16-Gbaud 16QAM", "20 km SSMF"],
            main_results=["Accuracy 95%"],
            limitations="仅用于测试",
            summary="一条用于数据库测试的论文记录。",
        ),
        retry_count=1,
        total_tokens=120,
        duration_ms=35,
        attempts=[
            ExtractionAttempt(
                attempt_number=1,
                stage=ExtractionStage.SUCCESS,
                raw_output='{"title":"测试论文"}',
                tokens=120,
                latency_ms=35,
            )
        ],
    )


def failed_file(filename: str = "损坏论文.pdf") -> BatchFileResult:
    return BatchFileResult(
        path=Path(filename),
        filename=filename,
        success=False,
        failure=ExtractionFailure(
            stage=ExtractionStage.PARSE,
            error_type="CorruptedDocumentError",
            error_msg="文件损坏",
            raw_llm_output=None,
        ),
        duration_ms=8,
    )


def batch_result() -> BatchResult:
    files = [successful_file(), failed_file()]
    return BatchResult(
        total_files=2,
        success_count=1,
        fail_count=1,
        total_tokens=120,
        duration_ms=50,
        files=files,
    )


def test_init_db_creates_three_tables_and_indexes(tmp_path: Path) -> None:
    path = tmp_path / "app.db"

    init_db(path)

    with sqlite3.connect(path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    assert {"tasks", "results", "failures"} <= names
    assert {"idx_results_task_id", "idx_failures_task_id"} <= indexes


def test_init_db_is_idempotent_and_keeps_existing_data(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    task_id = save_batch(batch_result(), path)

    init_db(path)

    assert get_task(task_id, path) is not None


def test_save_batch_splits_success_and_failure_rows(tmp_path: Path) -> None:
    path = tmp_path / "app.db"

    task_id = save_batch(batch_result(), path)

    task = get_task(task_id, path)
    results = get_results(task_id, path)
    failures = get_failures(task_id, path)
    assert task is not None
    assert task["status"] == "completed"
    assert task["total_files"] == 2
    assert task["success_count"] == 1
    assert task["fail_count"] == 1
    assert task["total_tokens"] == 120
    assert len(results) == 1
    assert len(failures) == 1
    assert results[0]["task_id"] == task_id
    assert failures[0]["task_id"] == task_id
    assert failures[0]["stage"] == "parse"


def test_list_fields_are_json_in_db_and_lists_when_queried(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    task_id = save_batch(batch_result(), path)

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT authors, experimental_conditions, main_results FROM results"
        ).fetchone()
    assert row is not None
    assert json.loads(row[0]) == ["张三", "Alice"]
    assert json.loads(row[1]) == ["16-Gbaud 16QAM", "20 km SSMF"]
    assert json.loads(row[2]) == ["Accuracy 95%"]

    result = get_results(task_id, path)[0]
    assert result["authors"] == ["张三", "Alice"]
    assert result["experimental_conditions"] == [
        "16-Gbaud 16QAM",
        "20 km SSMF",
    ]


def test_legacy_datasets_column_is_migrated_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    legacy_schema = db_module.SCHEMA_SQL.replace(
        "experimental_conditions TEXT NOT NULL",
        "datasets TEXT NOT NULL",
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(legacy_schema)
        connection.execute(
            """
            INSERT INTO tasks (
                created_at, finished_at, status, total_files,
                success_count, fail_count, total_tokens, duration_ms
            ) VALUES ('now', 'now', 'completed', 1, 1, 0, 0, 0)
            """
        )
        connection.execute(
            """
            INSERT INTO results (
                task_id, filename, title, authors, year, venue, doc_type,
                problem, method_name, datasets, main_results, limitations,
                summary, retry_count, tokens, latency_ms, raw_llm_output
            ) VALUES (
                1, 'legacy.pdf', 'Legacy', '["Alice"]', 2024, 'OE',
                'journal_article', 'problem', 'method', '["legacy value"]',
                '[]', NULL, 'summary', 0, 0, 0, NULL
            )
            """
        )
        connection.commit()

    init_db(path)
    result = get_results(1, path)[0]

    assert result["experimental_conditions"] == ["legacy value"]
    with sqlite3.connect(path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(results)")
        }
    assert "experimental_conditions" in columns
    assert "datasets" not in columns


def test_success_raw_output_and_metrics_are_saved(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    task_id = save_batch(batch_result(), path)

    result = get_results(task_id, path)[0]

    assert result["raw_llm_output"] == '{"title":"测试论文"}'
    assert result["retry_count"] == 1
    assert result["tokens"] == 120
    assert result["latency_ms"] == 35


def test_foreign_keys_reject_orphan_rows(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    init_db(path)

    with db_module.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO failures (
                    task_id, filename, stage, error_type, error_msg,
                    raw_output, retry_count, created_at
                ) VALUES (999, 'orphan.pdf', 'parse', 'Error', 'bad', NULL, 0, 'now')
                """
            )


def test_transaction_rolls_back_every_table_on_insert_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "app.db"

    def fail_insert(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(db_module, "_insert_failure", fail_insert)

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        save_batch(batch_result(), path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM failures").fetchone()[0] == 0


def test_missing_task_returns_none_and_empty_children(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    init_db(path)

    assert get_task(999, path) is None
    assert get_results(999, path) == []
    assert get_failures(999, path) == []
