"""开发集验证入口的参数约束测试。"""

from __future__ import annotations

import sys

import pytest

from eval import run_development_validation


def test_development_validation_rejects_negative_repair_retries(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_development_validation",
            "--confirm-cost",
            "--repair-retries",
            "-1",
        ],
    )

    with pytest.raises(SystemExit):
        run_development_validation.main()
