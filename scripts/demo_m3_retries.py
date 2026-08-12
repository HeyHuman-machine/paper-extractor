"""M3 本地演示：不访问网络，展示两种失败如何被自动修正。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings
from app.extractor import Extractor
from app.models import LLMResponse
from app.prompts import FEW_SHOT_RESULT


class DemoLLMClient:
    """依次返回非 JSON、缺字段 JSON 和正确 JSON。"""

    def __init__(self) -> None:
        invalid_record = {**FEW_SHOT_RESULT}
        invalid_record.pop("title")
        self.outputs = iter(
            [
                "这是第一次错误输出，不是 JSON。",
                json.dumps(invalid_record, ensure_ascii=False),
                json.dumps(FEW_SHOT_RESULT, ensure_ascii=False),
            ]
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> LLMResponse:
        return LLMResponse(
            content=next(self.outputs),
            model="local-demo",
            prompt_tokens=80,
            completion_tokens=20,
            total_tokens=100,
            latency_ms=5,
        )


def demo_settings() -> Settings:
    """返回演示专用假配置，不读取真实 API Key。"""

    return Settings.from_env(
        {
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": "https://example.invalid/v1",
            "LLM_MODEL": "local-demo",
            "LLM_API_KEY": "test-key-not-real",
            "LLM_TIMEOUT": "60",
            "LLM_MAX_RETRIES": "2",
            "LLM_THINKING_ENABLED": "false",
            "LLM_JSON_MODE": "true",
            "EXTRACT_MAX_CHARS": "12000",
            "BATCH_CONCURRENCY": "3",
        }
    )


def main() -> int:
    result = Extractor(demo_settings(), DemoLLMClient()).extract(
        "A fictional TinySort paper for the local M3 retry demo."
    )

    print("M3 三级容错本地演示（不访问 DeepSeek、不产生费用）")
    for attempt in result.attempts:
        print(
            f"#{attempt.attempt_number} stage={attempt.stage.value} "
            f"error={attempt.error_type or '-'}"
        )
    print(f"最终成功：{result.success}")
    print(f"字段修正重试：{result.retry_count}")
    print(f"总 token（演示值）：{result.total_tokens}")
    if result.record:
        print(f"最终标题：{result.record.title}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
