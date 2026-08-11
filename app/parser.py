"""PDF 和 DOCX 文档解析。

本模块只负责把文档转换成文本，不调用 LLM，也不抽取论文的11个业务字段。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import pdfplumber
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError

from app.models import ParsedDoc


MIN_TEXT_CHARS = 100
TRUNCATION_MARKER = "\n\n...[中间内容已截断]...\n\n"
SUPPORTED_SUFFIXES = {".pdf", ".docx"}


class DocumentParserError(Exception):
    """所有可预期文档解析错误的基类。"""


class DocumentNotFoundError(DocumentParserError):
    """输入文件不存在。"""


class UnsupportedFormatError(DocumentParserError):
    """输入文件不是当前支持的格式。"""


class EncryptedPDFError(DocumentParserError):
    """PDF 已加密且没有可用密码。"""


class SuspectedScannedPDFError(DocumentParserError):
    """PDF 几乎提取不到文字，疑似扫描件。"""


class CorruptedDocumentError(DocumentParserError):
    """PDF 或 DOCX 文件损坏，无法正常读取。"""


def parse_document(path: Path) -> ParsedDoc:
    """解析 PDF 或 DOCX 文件。

    参数：
        path: 待解析文件的路径。

    返回：
        包含全文、页数、逐页文本和文件元信息的 ``ParsedDoc``。

    异常：
        DocumentNotFoundError: 文件不存在。
        UnsupportedFormatError: 文件格式不受支持。
        EncryptedPDFError: PDF 已加密。
        SuspectedScannedPDFError: 提取文本少于100字符。
        CorruptedDocumentError: 文件损坏或结构无法读取。
    """

    document_path = Path(path).expanduser().resolve()
    if not document_path.is_file():
        raise DocumentNotFoundError(f"文件不存在：{document_path}")

    suffix = document_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise UnsupportedFormatError(
            f"不支持的文件格式 {suffix or '（无扩展名）'}；当前仅支持：{supported}"
        )

    if suffix == ".pdf":
        return _parse_pdf(document_path)
    return _parse_docx(document_path)


def smart_truncate(text: str, max_chars: int) -> str:
    """按“前70% + 后30%”策略截断长文本。

    论文前部通常包含标题、摘要和引言，尾部通常包含结论与局限性，因此不能只
    保留开头。返回值长度不会超过 ``max_chars``。

    参数：
        text: 原始全文。
        max_chars: 允许保留的最大字符数。

    返回：
        未超长时返回原文；超长时返回首尾文本及中间截断标记。
    """

    if max_chars <= len(TRUNCATION_MARKER):
        raise ValueError(
            f"max_chars 必须大于截断标记长度 {len(TRUNCATION_MARKER)}"
        )
    if len(text) <= max_chars:
        return text

    available_chars = max_chars - len(TRUNCATION_MARKER)
    head_chars = int(available_chars * 0.7)
    tail_chars = available_chars - head_chars
    return f"{text[:head_chars]}{TRUNCATION_MARKER}{text[-tail_chars:]}"


def _parse_pdf(path: Path) -> ParsedDoc:
    """使用 pdfplumber 解析文本型 PDF。"""

    try:
        # 显式管理二进制文件流，保证 pdfplumber 在构造阶段报错时也能释放句柄。
        # 这在 Windows 上尤其重要，否则损坏文件可能一直处于“正在使用”状态。
        with path.open("rb") as file_stream:
            with pdfplumber.open(file_stream) as pdf:
                if not pdf.pages:
                    raise CorruptedDocumentError(
                        f"PDF 没有可读取的页面：{path.name}"
                    )

                pages = [
                    (page.extract_text() or "").strip() for page in pdf.pages
                ]
                text = "\n\n".join(
                    page_text for page_text in pages if page_text
                ).strip()
                if len(text) < MIN_TEXT_CHARS:
                    raise SuspectedScannedPDFError(
                        f"PDF 仅提取到 {len(text)} 个字符，疑似扫描件或图片型 PDF："
                        f"{path.name}。当前版本不做 OCR。"
                    )

                metadata = _build_file_metadata(path)
                metadata.update(_clean_pdf_metadata(pdf.metadata or {}))

                return ParsedDoc(
                    path=path,
                    file_name=path.name,
                    file_type="pdf",
                    page_count=len(pdf.pages),
                    text=text,
                    pages=pages,
                    metadata=metadata,
                )
    except (EncryptedPDFError, SuspectedScannedPDFError, CorruptedDocumentError):
        raise
    except PDFPasswordIncorrect as exc:
        raise EncryptedPDFError(
            f"PDF 已加密，需要密码才能读取：{path.name}"
        ) from exc
    except (PDFSyntaxError, OSError, ValueError) as exc:
        raise CorruptedDocumentError(
            f"PDF 文件可能已经损坏，无法读取：{path.name}"
        ) from exc
    except Exception as exc:
        raise CorruptedDocumentError(
            f"PDF 文件可能已经损坏，无法读取：{path.name}"
            f"（底层错误：{type(exc).__name__}）"
        ) from exc


def _parse_docx(path: Path) -> ParsedDoc:
    """使用 python-docx 解析 Word 文档。

    DOCX 本身不保存可靠的分页结果，所以这里把整个文档视为一个逻辑页。
    """

    try:
        document = Document(path)
        blocks: list[str] = []
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    blocks.append(text)
            elif isinstance(block, Table):
                for row in block.rows:
                    row_text = "\t".join(cell.text.strip() for cell in row.cells)
                    if row_text.strip():
                        blocks.append(row_text)

        text = "\n\n".join(blocks).strip()
        if len(text) < MIN_TEXT_CHARS:
            raise CorruptedDocumentError(
                f"DOCX 提取到的有效文本少于 {MIN_TEXT_CHARS} 个字符：{path.name}"
            )

        properties = document.core_properties
        metadata = _build_file_metadata(path)
        metadata.update(
            {
                "title": properties.title or None,
                "author": properties.author or None,
                "subject": properties.subject or None,
                "keywords": properties.keywords or None,
                "created": properties.created.isoformat()
                if properties.created
                else None,
                "modified": properties.modified.isoformat()
                if properties.modified
                else None,
            }
        )

        return ParsedDoc(
            path=path,
            file_name=path.name,
            file_type="docx",
            page_count=1,
            text=text,
            pages=[text],
            metadata=metadata,
        )
    except CorruptedDocumentError:
        raise
    except (PackageNotFoundError, BadZipFile, KeyError, OSError, ValueError) as exc:
        raise CorruptedDocumentError(
            f"DOCX 文件可能已经损坏，无法读取：{path.name}"
        ) from exc
    except Exception as exc:
        raise CorruptedDocumentError(
            f"DOCX 文件可能已经损坏，无法读取：{path.name}"
            f"（底层错误：{type(exc).__name__}）"
        ) from exc


def _build_file_metadata(path: Path) -> dict[str, Any]:
    """读取不依赖文档格式的基础文件信息。"""

    stat = path.stat()
    return {
        "file_size_bytes": stat.st_size,
        "suffix": path.suffix.lower(),
        "modified_timestamp": stat.st_mtime,
    }


def _clean_pdf_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """把 PDF 元信息转换成适合序列化的简单值。"""

    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized_key = str(key).lstrip("/").lower()
        if value is None or isinstance(value, (str, int, float, bool)):
            cleaned[normalized_key] = value
        else:
            cleaned[normalized_key] = str(value)
    return cleaned
