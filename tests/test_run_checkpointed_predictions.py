import json
from pathlib import Path

from app.config import get_settings
from eval.run_checkpointed_predictions import _load_checkpoint, _write_checkpoint


def test_checkpoint_round_trip(tmp_path):
    target = tmp_path / "predictions.json"
    settings = get_settings()
    payload = _load_checkpoint(target, settings, 2)
    payload["results"].append({"filename": "paper.pdf", "tokens": 12})

    _write_checkpoint(target, payload, 1, 20)

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["summary"] == {"total_files": 1, "success_count": 1, "fail_count": 0, "total_tokens": 12, "duration_ms": 20}
