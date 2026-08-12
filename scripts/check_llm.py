"""M2 独立验收：用虚构短文本完成一次最小 DeepSeek 调用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import ConfigurationError
from app.llm import LLMError, chat
from app.models import PaperRecord
from app.prompts import FEW_SHOT_TEXT, build_extraction_messages


def main() -> int:
    """调用真实 API，并用 PaperRecord 做第一道结果验收。"""

    print("正在发送非敏感的虚构论文短文本，不会上传 data/inbox 中的论文……")
    try:
        response = chat(
            build_extraction_messages(FEW_SHOT_TEXT),
            max_tokens=1000,
            temperature=0.0,
        )
        record = PaperRecord.model_validate(json.loads(response.content))
    except (ConfigurationError, LLMError, ValueError) as exc:
        print(f"M2 调用失败：{exc}")
        return 1

    print("M2 DeepSeek 调用成功")
    print(f"模型：{response.model}")
    print(f"输入 token：{response.prompt_tokens}")
    print(f"输出 token：{response.completion_tokens}")
    print(f"总 token：{response.total_tokens}")
    print(f"耗时：{response.latency_ms} ms")
    print(f"重试次数：{response.retry_count}")
    print("结构化结果：")
    print(record.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
