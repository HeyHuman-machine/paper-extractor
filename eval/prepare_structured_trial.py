"""根据已冻结的 B2 清单创建结构化字段试点标注模板。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.metrics import safe_label_filename
from eval.structured_trial import structured_template


def prepare_structured_templates(manifest_path: Path | str, output_dir: Path | str) -> list[Path]:
    """创建空白模板；任何已有模板均不覆盖。"""

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list) or not all(isinstance(name, str) and name.strip() for name in files):
        raise ValueError("B2 清单必须包含非空 files 数组")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for filename in files:
        target = destination / safe_label_filename(filename)
        if target.exists():
            continue
        target.write_text(
            json.dumps(structured_template(filename), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(target)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 B2 结构化字段试点标注模板")
    parser.add_argument("--manifest", type=Path, default=Path("eval/b2_pilot_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("eval/ground_truth_structured_trial"))
    args = parser.parse_args()
    created = prepare_structured_templates(args.manifest, args.output_dir)
    print(f"新建 {len(created)} 份 B2 空白模板；已有文件未覆盖。")
    print("请逐篇依据原论文填写两个结构化列表，再把 needs_review 改为 false。")


if __name__ == "__main__":
    main()
