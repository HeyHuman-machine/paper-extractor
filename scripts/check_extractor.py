"""M3 独立验收：用虚构论文文本运行三级容错抽取器。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.extractor import extract
from app.prompts import FEW_SHOT_TEXT


def main() -> int:
    print("正在抽取非敏感的虚构论文文本，不会读取 data/inbox……")
    result = extract(FEW_SHOT_TEXT)

    print(f"成功：{result.success}")
    print(f"字段修正重试：{result.retry_count}")
    print(f"总 token：{result.total_tokens}")
    print(f"总耗时：{result.total_latency_ms} ms")
    print("尝试过程：")
    for attempt in result.attempts:
        status = attempt.stage.value
        detail = f"，错误：{attempt.error_msg}" if attempt.error_msg else ""
        print(
            f"  #{attempt.attempt_number} {status}，"
            f"token={attempt.tokens}，耗时={attempt.latency_ms} ms{detail}"
        )

    if result.success and result.record:
        print("结构化结果：")
        print(result.record.model_dump_json(indent=2))
        return 0

    print("最终失败诊断：")
    print(result.failure.model_dump_json(indent=2) if result.failure else "未知")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
