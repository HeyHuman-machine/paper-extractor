"""B0 命令行入口：真实运行三档三级容错消融实验。"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import get_settings
from app.pipeline import discover_documents
from eval.ablation import run_ablation, score_ablation, write_ablation_report


def main() -> None:
    parser = argparse.ArgumentParser(description="B0：三级容错消融实验（真实调用 DeepSeek）")
    parser.add_argument("--input-dir", type=Path, default=Path("literature/optical-communications/evaluation"))
    parser.add_argument("--ground-truth", type=Path, default=Path("eval/ground_truth/evaluation"))
    parser.add_argument("--output-dir", type=Path, default=Path("eval/output/ablation-b0"))
    parser.add_argument("--confirm-cost", action="store_true", help="确认执行 30 篇 x 3 档的真实 DeepSeek 调用")
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("B0 会真实调用 DeepSeek 三档；确认后加 --confirm-cost")
    settings = get_settings()
    files = discover_documents(args.input_dir)
    if len(files) != 30:
        raise ValueError(f"B0 必须固定使用 30 篇盲测论文，当前发现 {len(files)} 篇")
    print(f"B0 开始：{len(files)} 篇 x 3 档，模型 {settings.llm_model}，并发 {settings.batch_concurrency}", flush=True)
    payload = score_ablation(run_ablation(files, settings), args.ground_truth)
    paths = write_ablation_report(payload, args.output_dir)
    print("B0 完成", flush=True)
    for name, path in paths.items():
        print(f"{name}: {path.resolve()}", flush=True)


if __name__ == "__main__":
    main()
