import json

from app.config import Settings
from eval import run_structured_trial as trial


def test_checkpoint_is_written_atomically_and_loaded(tmp_path) -> None:
    settings = Settings.from_env(
        {
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": "https://example.com/v1",
            "LLM_MODEL": "test-model",
            "LLM_API_KEY": "test-key",
            "LLM_TIMEOUT": "60",
            "LLM_MAX_RETRIES": "2",
            "LLM_THINKING_ENABLED": "false",
            "LLM_JSON_MODE": "true",
            "EXTRACT_MAX_CHARS": "12000",
            "BATCH_CONCURRENCY": "1",
        }
    )
    payload = trial._build_payload(
        settings,
        2,
        ["paper.pdf"],
        [{"filename": "paper.pdf", "record": {}, "tokens": 42}],
        [],
    )
    checkpoint = tmp_path / "checkpoint.json"

    trial._write_checkpoint(checkpoint, payload)
    loaded = trial._load_checkpoint(checkpoint, settings, 2)

    assert checkpoint.exists()
    assert not checkpoint.with_suffix(".json.tmp").exists()
    assert loaded["results"][0]["filename"] == "paper.pdf"


def test_invalid_checkpoint_is_not_silently_overwritten(tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("not json", encoding="utf-8")
    settings = type("Settings", (), {"llm_model": "test"})()

    try:
        trial._load_checkpoint(checkpoint, settings, 2)
    except ValueError as exc:
        assert "拒绝覆盖" in str(exc)
    else:
        raise AssertionError("无效检查点必须阻止覆盖")


def test_checkpoint_output_directory_must_exist(tmp_path) -> None:
    missing_output = tmp_path / "missing" / "checkpoint.json"

    try:
        trial.ensure_checkpoint_writable(missing_output)
    except RuntimeError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("不存在的检查点目录必须阻止 API 运行")


def test_retry_failures_keeps_only_successful_checkpoint_items(tmp_path, monkeypatch) -> None:
    settings = type("Settings", (), {"llm_model": "test", "extract_max_chars": 12000})()
    checkpoint = tmp_path / "checkpoint.json"
    trial._write_checkpoint(
        checkpoint,
        trial._build_payload(
            settings,
            2,
            ["success.pdf", "failed.pdf"],
            [{"filename": "success.pdf", "record": {}, "tokens": 1}],
            [{"filename": "failed.pdf", "error_type": "ConnectError"}],
        ),
    )
    monkeypatch.setattr(trial, "get_settings", lambda: settings)

    class FakeClient:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None

    monkeypatch.setattr(trial, "LLMClient", lambda settings: FakeClient())
    payload = trial.run_structured_trial(
        tmp_path, ["success.pdf"], repair_retries=0, checkpoint_path=checkpoint, retry_failures=True
    )

    assert payload["results"][0]["filename"] == "success.pdf"
    assert payload["failures"] == []
