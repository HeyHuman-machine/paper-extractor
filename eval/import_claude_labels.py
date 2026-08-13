"""将 Claude 分批复核的连续 JSON 数组整理为 M9 标注草稿。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from app.models import PaperRecord
from eval.metrics import safe_label_filename


def _document_key(filename: str) -> str:
    """忽略连字符、空格和大小写，稳定地匹配同一篇论文。"""

    return re.sub(r"[^a-z0-9]", "", Path(filename).stem.casefold())


def _load_concatenated_arrays(source: Path) -> list[dict[str, Any]]:
    """读取 ``[...][...]`` 形式的连续 JSON 数组，而非要求用户手工合并。"""

    content = source.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    offset = 0
    records: list[dict[str, Any]] = []
    while offset < len(content):
        while offset < len(content) and content[offset].isspace():
            offset += 1
        if offset == len(content):
            break
        payload, offset = decoder.raw_decode(content, offset)
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise ValueError("每一批 Claude 结果都必须是由对象组成的 JSON 数组")
        records.extend(payload)
    return records


def _trim_at_sentence_boundary(text: str, limit: int) -> str:
    """仅在字段上限处截到已结束的句子，避免写入无法通过 schema 的草稿。"""

    text = text.strip()
    if len(text) <= limit:
        return text
    boundaries = [
        index + 1
        for index, character in enumerate(text[:limit])
        if character in "。！？；.!?;"
    ]
    if boundaries:
        return text[: boundaries[-1]].rstrip()
    return f"{text[: limit - 1].rstrip()}…"


def _normalize_record(raw_record: dict[str, Any]) -> dict[str, Any]:
    """保留原有结论，只处理 schema 上限与 Claude 的多余空键。"""

    allowed = set(PaperRecord.model_fields)
    record = {key: value for key, value in raw_record.items() if key in allowed}
    for field, limit in (("problem", 200), ("summary", 400)):
        value = record.get(field)
        if isinstance(value, str):
            record[field] = _trim_at_sentence_boundary(value, limit)
    return PaperRecord.model_validate(record).model_dump(mode="json")


def import_claude_labels(
    source: Path | str,
    input_dir: Path | str,
    output_dir: Path | str,
    *,
    overwrite: bool = False,
) -> list[Path]:
    """导入、匹配并校验 Claude 草稿；不把它们自动升级为已确认金标准。"""

    documents = [
        path
        for path in Path(input_dir).iterdir()
        if path.is_file() and path.suffix.casefold() in {".pdf", ".docx"}
    ]
    lookup = {_document_key(path.name): path.name for path in documents}
    if len(lookup) != len(documents):
        raise ValueError("输入目录中存在归一化后重名的论文，无法安全匹配")

    imported: list[Path] = []
    seen: set[str] = set()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for item in _load_concatenated_arrays(Path(source)):
        source_name = str(item.get("filename", "")).strip()
        filename = lookup.get(_document_key(source_name))
        if not filename:
            raise ValueError(f"找不到 Claude 结果对应的本地论文：{source_name}")
        if filename in seen:
            raise ValueError(f"Claude 结果包含重复论文：{filename}")
        seen.add(filename)

        raw_record = item.get("record")
        if not isinstance(raw_record, dict):
            raise ValueError(f"{source_name} 缺少 record 对象")
        target = destination / safe_label_filename(filename)
        if target.exists() and not overwrite:
            continue

        metadata = dict(item.get("annotation_meta") or {})
        metadata.update(
            {
                "split": "evaluation",
                "review_status": "claude_reviewed_pending_user_confirmation",
                "reviewed_by": "Claude",
                "source_filename": source_name,
            }
        )
        draft = {
            "filename": filename,
            "needs_review": True,
            "annotation_meta": metadata,
            "record": _normalize_record(raw_record),
            "evidence": item.get("evidence") or {},
        }
        target.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        imported.append(target)

    missing = sorted(set(lookup.values()) - seen)
    if missing:
        raise ValueError(f"Claude 结果缺少 {len(missing)} 篇论文：{', '.join(missing)}")
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 Claude M9 标注草稿")
    parser.add_argument("source", type=Path, help="包含连续 JSON 数组的 Claude 汇总文本")
    parser.add_argument("--input-dir", type=Path, required=True, help="30 篇盲测论文目录")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("eval/ground_truth/evaluation")
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖同名的空白模板")
    args = parser.parse_args()
    imported = import_claude_labels(
        args.source, args.input_dir, args.output_dir, overwrite=args.overwrite
    )
    print(f"已导入 {len(imported)} 份 Claude 审阅草稿；全部仍为 needs_review=true。")


if __name__ == "__main__":
    main()
