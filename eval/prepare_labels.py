"""根据已有 M6 JSON 生成待人工核对的 M9 标注草稿。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.models import PaperRecord
from eval.metrics import safe_label_filename


SUPPORTED_INPUT_SUFFIXES = {".pdf", ".docx"}


def prepare_labels(source: Path | str, output_dir: Path | str) -> list[Path]:
    """复制成功抽取结果为草稿；已有标注绝不覆盖。"""

    payload = json.loads(Path(source).read_text(encoding="utf-8"))
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("M6 JSON 必须包含 results 数组")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for item in results:
        if not isinstance(item, dict) or not item.get("filename"):
            continue
        record = PaperRecord.model_validate(item)
        target = destination / safe_label_filename(str(item["filename"]))
        if target.exists():
            continue
        draft: dict[str, Any] = {
            "filename": item["filename"],
            "needs_review": True,
            "record": record.model_dump(mode="json"),
        }
        target.write_text(
            json.dumps(draft, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(target)
    return created


def prepare_blank_labels(input_dir: Path | str, output_dir: Path | str) -> list[Path]:
    """仅按论文文件名创建空白草稿，不读取或复制 LLM 预测内容。"""

    source = Path(input_dir)
    if not source.is_dir():
        raise NotADirectoryError(f"论文目录不存在：{source}")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for document in sorted(source.iterdir()):
        if not document.is_file() or document.suffix.casefold() not in SUPPORTED_INPUT_SUFFIXES:
            continue
        target = destination / safe_label_filename(document.name)
        if target.exists():
            continue
        draft: dict[str, Any] = {
            "filename": document.name,
            "needs_review": True,
            "annotation_meta": {
                "split": "evaluation",
                "review_status": "blank_pending_independent_annotation",
                "reviewed_by": None,
                "reviewed_at": None,
                "pages_checked": None,
                "human_attention_fields": [],
                "note": "独立盲测空白模板；填写标准答案时不得查看本轮 DeepSeek 预测。",
            },
            "record": {
                "title": "",
                "authors": [],
                "year": None,
                "venue": None,
                "doc_type": "journal_article",
                "problem": "",
                "method_name": None,
                "experimental_conditions": [],
                "main_results": [],
                "limitations": None,
                "summary": "",
            },
            "evidence": {},
        }
        target.write_text(
            json.dumps(draft, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(target)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 M9 人工标注草稿")
    parser.add_argument("source", type=Path, nargs="?", help="M6 导出的论文完整数据.json")
    parser.add_argument(
        "--blank-from-dir",
        type=Path,
        help="仅按目录中的 PDF/DOCX 文件名生成空白模板，不读取模型预测",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval/ground_truth/evaluation"),
        help="标注草稿目录",
    )
    args = parser.parse_args()
    if args.blank_from_dir is not None:
        if args.source is not None:
            parser.error("source 与 --blank-from-dir 不能同时使用")
        created = prepare_blank_labels(args.blank_from_dir, args.output_dir)
    else:
        if args.source is None:
            parser.error("必须提供 source 或 --blank-from-dir")
        created = prepare_labels(args.source, args.output_dir)
    print(f"新建 {len(created)} 份标注草稿；已有文件未覆盖。")
    print("请逐篇对照原论文修正 record，确认后把 needs_review 改为 false。")


if __name__ == "__main__":
    main()
