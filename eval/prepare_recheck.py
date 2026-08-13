"""A1：为独立复核创建只含三个低分字段的空白标注文件。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.metrics import safe_label_filename


def prepare_recheck_templates(manifest_path: Path, output_dir: Path) -> list[Path]:
    """从固定样本清单生成空白模板，绝不读取旧的 ground truth 内容。"""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filenames = manifest.get("files")
    if not isinstance(filenames, list) or not all(isinstance(item, str) for item in filenames):
        raise ValueError("清单必须包含字符串数组 files")
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for filename in filenames:
        path = output_dir / safe_label_filename(filename)
        if path.exists():
            continue
        payload = {
            "filename": filename,
            "needs_review": True,
            "annotation_meta": {
                "split": "agreement_recheck",
                "reviewer": "independent_ai_reviewer",
                "instruction": "只依据原 PDF 填写三个字段；不要查看 ground_truth/evaluation。",
            },
            "review": {
                "method_name": None,
                "experimental_conditions": [],
                "main_results": [],
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        created.append(path)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 A1 独立复核空白模板")
    parser.add_argument(
        "--manifest", type=Path, default=Path("eval/recheck_manifest.json")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("eval/ground_truth_recheck")
    )
    args = parser.parse_args()
    created = prepare_recheck_templates(args.manifest, args.output_dir)
    print(f"已创建 {len(created)} 份独立复核模板：{args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
