"""独立检查 data/inbox 中的真实论文解析结果。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 直接运行本文件时，Python 默认只认识 scripts 目录；这里补上项目根目录。
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.parser import DocumentParserError, parse_document


DEFAULT_INBOX = PROJECT_ROOT / "data" / "inbox"


def main() -> int:
    """解析命令行指定文件，未指定时解析 inbox 中全部 PDF/DOCX。"""

    parser = argparse.ArgumentParser(description="检查 PDF/DOCX 文本解析结果")
    parser.add_argument("paths", nargs="*", type=Path, help="待解析文档路径")
    args = parser.parse_args()

    paths = args.paths or sorted(
        [*DEFAULT_INBOX.glob("*.pdf"), *DEFAULT_INBOX.glob("*.docx")]
    )
    if not paths:
        print(f"没有找到待检查文档：{DEFAULT_INBOX}")
        return 1

    failed_count = 0
    for path in paths:
        print("=" * 72)
        print(f"文件：{path.name}")
        try:
            document = parse_document(path)
        except DocumentParserError as exc:
            failed_count += 1
            print(f"解析失败：{exc}")
            continue

        print(f"格式：{document.file_type}")
        print(f"页数：{document.page_count}")
        print(f"字符数：{len(document.text)}")
        print("前500字：")
        print(document.text[:500])

    print("=" * 72)
    print(f"检查完成：共 {len(paths)} 篇，成功 {len(paths) - failed_count} 篇，失败 {failed_count} 篇")
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
