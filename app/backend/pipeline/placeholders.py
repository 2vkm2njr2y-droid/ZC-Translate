"""Placeholder protection for code, URLs, markup and template variables.

Placeholders are rendered as ``⟦0⟧`` style tokens.  They are unlikely to be
translated, easy to verify, and do not collide with normal punctuation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PLACEHOLDER_RE = re.compile(r"⟦\s*(\d+)\s*⟧")
PLACEHOLDER_FORMAT = "⟦0⟧"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fence", re.compile(r"```[\s\S]*?```")),
    ("url", re.compile(r"https?://[^\s<>\"'）)】]+")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("html", re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]*)?/?>")),
    ("inline_code", re.compile(r"`[^`\n]+`")),
    ("jinja2", re.compile(r"\{\{[\s\S]*?\}\}")),
    ("template", re.compile(r"\$\{[^{}\n]+\}")),
    ("brace", re.compile(r"\{[A-Za-z_][A-Za-z0-9_.\[\]]*\}")),
    ("printf", re.compile(r"%[sdifr]")),
    ("winpath", re.compile(r"[A-Za-z]:\\[^\s<>\"'|]+")),
    ("hex", re.compile(r"\b[0-9a-fA-F]{16,}\b")),
]


@dataclass
class ProtectedText:
    masked: str
    mapping: dict[int, str]

    @property
    def count(self) -> int:
        return len(self.mapping)

    def restore(self, text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            key = int(match.group(1))
            return self.mapping.get(key, match.group(0))

        return PLACEHOLDER_RE.sub(repl, text)

    def missing_keys(self, text: str) -> list[int]:
        found = {int(m.group(1)) for m in PLACEHOLDER_RE.finditer(text)}
        return sorted(set(self.mapping) - found)

    def duplicated_keys(self, text: str) -> list[int]:
        counts: dict[int, int] = {}
        for match in PLACEHOLDER_RE.finditer(text):
            key = int(match.group(1))
            counts[key] = counts.get(key, 0) + 1
        return sorted(key for key, count in counts.items() if count > 1)


def protect(text: str) -> ProtectedText:
    # Collect non-overlapping matches in priority order.
    occupied: list[tuple[int, int]] = []
    matches: list[tuple[int, int, str]] = []
    for _, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if start == end:
                continue
            if any(start < other_end and end > other_start for other_start, other_end in occupied):
                continue
            occupied.append((start, end))
            matches.append((start, end, match.group(0)))

    if not matches:
        return ProtectedText(masked=text, mapping={})

    matches.sort(key=lambda item: item[0])
    output: list[str] = []
    mapping: dict[int, str] = {}
    cursor = 0
    for idx, (start, end, value) in enumerate(matches):
        output.append(text[cursor:start])
        output.append(f"⟦{idx}⟧")
        mapping[idx] = value
        cursor = end
    output.append(text[cursor:])
    return ProtectedText(masked="".join(output), mapping=mapping)


def instruction(mapping: dict[int, str], chinese: bool) -> str:
    if not mapping:
        return ""
    tokens = "、".join(f"⟦{idx}⟧" for idx in sorted(mapping)[:8])
    if len(mapping) > 8:
        tokens += " 等"
    if chinese:
        return (f"译文中必须保留等量的占位符（例如 {tokens}），"
                "绝对不可遗漏、改写或翻译该符号，并注意占位符的位置。")
    return (f"You must retain the exact same number of placeholders "
            f"(for example {tokens}). Strictly do not omit, rewrite or translate "
            "these symbols, and pay close attention to their placement.")
