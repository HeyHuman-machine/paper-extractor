"""用开发集验证新的抽取 Prompt，不参与最终 M9 盲测成绩。"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import get_settings
from app.pipeline import discover_documents
from eval.run_predictions import run_prediction_round, write_predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="运行单轮开发集 Prompt 验证")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("literature/optical-communications/seed"),
        help="仅用于调试 Prompt 的开发集目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/predictions/v2-development/predictions.json"),
    )
    parser.add_argument(
        "--label",
        default="V2 原子化 Prompt 开发集验证",
        help="写入预测文件、用于版本报告的可读标签",
    )
    parser.add_argument(
        "--repair-retries",
        type=int,
        default=2,
        help="M3 内容修复上限；版本对比时两边必须使用相同值",
    )
    parser.add_argument(
        "--evidence-aware",
        action="store_true",
        help="使用 V4 全文证据片段选择；默认保持 V2 抽取方式",
    )
    parser.add_argument(
        "--evidence-strategy",
        choices=("sections", "keywords"),
        default=None,
        help="V4 使用 sections；V5 使用 keywords。指定后优先于 --evidence-aware",
    )
    parser.add_argument(
        "--confirm-cost",
        action="store_true",
        help="确认会向 LLM 发送开发集论文并产生费用",
    )
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("此命令会真实调用 LLM；确认后加 --confirm-cost")
    if args.repair_retries < 0:
        parser.error("--repair-retries 不能小于 0")

    settings = get_settings()
    files = discover_documents(args.input_dir)
    if not files:
        raise FileNotFoundError("开发集目录没有 PDF / DOCX")
    print(f"开发集验证：{len(files)} 篇论文", flush=True)
    batch = run_prediction_round(
        files,
        settings,
        max_repair_retries=args.repair_retries,
        evidence_aware=args.evidence_aware,
        evidence_strategy=args.evidence_strategy,
    )
    output = write_predictions(
        batch,
        args.output,
        label=args.label,
        max_repair_retries=args.repair_retries,
        settings=settings,
    )
    print(f"预测已保存：{output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
