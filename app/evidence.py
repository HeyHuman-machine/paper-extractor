"""V4 证据片段选择：从全文挑出最适合字段抽取的可核查原文。"""

from __future__ import annotations

import re


SECTION_MARKER = "\n\n===== {label} =====\n"
_METHOD_PATTERN = re.compile(
    r"(?im)^.*(?:we\s+(?:propose|present|introduce|develop)|proposed\s+"
    r"(?:method|scheme|approach)|method(?:ology)?|architecture|scheme).*$"
)
_EXPERIMENT_PATTERN = re.compile(
    r"(?im)^.*(?:experimental|experiment|simulation|results?|performance|"
    r"setup|measurement|table\s*\d+|fig(?:ure)?\.\s*\d+).*$"
)
_CONDITION_PATTERN = re.compile(
    r"(?i)\b(?:\d+(?:\.\d+)?\s*(?:tbaud|gbaud|mbaud|gb/s|gbps|km|m|"
    r"dbm|thz|ghz|nm|gsa/s)|\d+\s*(?:qam|qpsk|bpsk|pam\d*))\b|"
    r"\b(?:modulation|baud(?:\s*rate)?|bit(?:\s*rate)?|fiber|ssmf|"
    r"wavelength|carrier(?:\s*frequency)?|received\s*(?:optical\s*)?power|"
    r"sampling(?:\s*rate)?|back-to-back)\b"
)
_RESULT_PATTERN = re.compile(
    r"(?i)\b(?:ber|bit\s*error\s*rate|fec|power\s*penalty|penalty|"
    r"sensitivity|receiver\s*power|rop|gain|improvement|error\s*rate|"
    r"below|threshold|achieve[ds]?)\b"
)


def build_evidence_bundle(text: str, max_chars: int) -> str:
    """返回带来源标签的论文片段，总长度不超过 ``max_chars``。

    V4 不把长论文机械截成“开头 + 结尾”。它始终保留论文开头和结尾，并从全文
    定位方法、实验、仿真、结果、图表附近的窗口。标签只用于提醒模型证据来源，
    不会成为输出字段的一部分。
    """

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("paper_text 不能为空")
    if max_chars < 800:
        raise ValueError("max_chars 至少需要 800，才能保留基本证据片段")
    if len(cleaned) <= 800:
        return cleaned

    # 预先给四段分配预算，避免前面的实验窗口把结论片段挤出上限。
    marker_budget = sum(
        len(SECTION_MARKER.format(label=label))
        for label in (
            "论文开头（题目、作者、摘要）",
            "方法命名证据",
            "实验 / 仿真 / 结果证据",
            "论文结尾（结论、局限性）",
        )
    )
    content_budget = max_chars - marker_budget
    head_budget = int(content_budget * 0.28)
    method_budget = int(content_budget * 0.18)
    tail_budget = int(content_budget * 0.17)
    experiment_budget = content_budget - head_budget - method_budget - tail_budget
    head = cleaned[:head_budget].strip()
    tail = cleaned[-tail_budget:].strip()

    method = _collect_windows(cleaned, _METHOD_PATTERN, method_budget)
    experiment = _collect_windows(cleaned, _EXPERIMENT_PATTERN, experiment_budget)
    sections = [("论文开头（题目、作者、摘要）", head)]
    sections.append(("方法命名证据", method or "（未定位到单独方法段）"))
    sections.append(("实验 / 仿真 / 结果证据", experiment or "（未定位到单独实验/结果段）"))
    sections.append(("论文结尾（结论、局限性）", tail))

    bundled = "".join(
        SECTION_MARKER.format(label=label) + content for label, content in sections
    ).strip()
    if len(bundled) > max_chars:
        raise AssertionError("证据片段预算计算错误：拼装结果超过上限")
    return bundled


def build_keyword_evidence_bundle(text: str, max_chars: int) -> str:
    """V5：用字段关键词和量纲而非章节标题定位条件、结果证据。

    PDF 转出的标题可能断行或丢失，但 ``20 km``、``-18 dBm``、``BER`` 等事实
    通常仍保留。因此 V5 将全文中这些命中的邻近原文分成条件、结果两组，再加上
    开头（元数据/方法）和结尾（局限性），并保持严格的长度预算。
    """

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("paper_text 不能为空")
    if max_chars < 800:
        raise ValueError("max_chars 至少需要 800，才能保留基本证据片段")
    if len(cleaned) <= 800:
        return cleaned

    labels = (
        "论文开头（题目、作者、摘要）",
        "方法命名证据",
        "条件数值证据（Gbaud / km / dBm 等）",
        "结果指标证据（BER / FEC / penalty 等）",
        "论文结尾（结论、局限性）",
    )
    marker_budget = sum(len(SECTION_MARKER.format(label=label)) for label in labels)
    content_budget = max_chars - marker_budget
    head_budget = int(content_budget * 0.24)
    method_budget = int(content_budget * 0.12)
    condition_budget = int(content_budget * 0.29)
    result_budget = int(content_budget * 0.23)
    tail_budget = content_budget - head_budget - method_budget - condition_budget - result_budget

    sections = [
        (labels[0], cleaned[:head_budget].strip()),
        (labels[1], _collect_windows(cleaned, _METHOD_PATTERN, method_budget) or "（未定位到单独方法命名证据）"),
        (labels[2], _collect_keyword_windows(cleaned, _CONDITION_PATTERN, condition_budget) or "（未定位到条件关键词证据）"),
        (labels[3], _collect_keyword_windows(cleaned, _RESULT_PATTERN, result_budget) or "（未定位到结果关键词证据）"),
        (labels[4], cleaned[-tail_budget:].strip()),
    ]
    bundled = "".join(
        SECTION_MARKER.format(label=label) + content for label, content in sections
    ).strip()
    if len(bundled) > max_chars:
        raise AssertionError("关键词证据片段预算计算错误：拼装结果超过上限")
    return bundled


def _collect_windows(text: str, pattern: re.Pattern[str], budget: int) -> str:
    """以命中行作为中心取若干窗口；重叠窗口只保留一次。"""

    windows: list[tuple[int, int]] = []
    for match in pattern.finditer(text):
        start = max(0, match.start() - 300)
        end = min(len(text), match.end() + 900)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
        if len(windows) >= 6:
            break

    pieces: list[str] = []
    remaining = budget
    for start, end in windows:
        if remaining <= 0:
            break
        excerpt = text[start:end].strip()
        if not excerpt:
            continue
        piece = excerpt[:remaining]
        pieces.append(piece)
        remaining -= len(piece)
    # 分隔符本身也占字符数；最后再截一次，保证调用方的总预算严格成立。
    return "\n\n...[同类证据片段省略]...\n\n".join(pieces)[:budget]


def _collect_keyword_windows(text: str, pattern: re.Pattern[str], budget: int) -> str:
    """围绕关键词/量纲命中提取窗口，合并重叠范围并保留全文不同位置的证据。"""

    windows: list[tuple[int, int]] = []
    for match in pattern.finditer(text):
        start = max(0, match.start() - 260)
        end = min(len(text), match.end() + 640)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
        if len(windows) >= 10:
            break

    separator = "\n\n...[同类证据片段省略]...\n\n"
    pieces: list[str] = []
    remaining = budget
    for index, (start, end) in enumerate(windows):
        separator_size = len(separator) if index else 0
        if remaining <= separator_size:
            break
        excerpt = text[start:end].strip()
        if not excerpt:
            continue
        piece_budget = remaining - separator_size
        pieces.append(excerpt[:piece_budget])
        remaining -= separator_size + len(pieces[-1])
    return separator.join(pieces)
