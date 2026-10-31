"""Paragraph / line segmentation with separator preservation.

A block keeps the separator that followed it in the source, so the translated
text can be reconstructed without collapsing blank lines or list formatting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import MAX_BLOCK_CHARS

_CJK_END = "。！？!?；;"
_CLOSERS = "」』”’）)】》〉\"'"
_PARA_SEP = re.compile(r"(\n{2,})")
_LINE_SEP = re.compile(r"(\n)")


@dataclass
class Block:
    index: int
    text: str
    sep_after: str = ""
    translate: bool = True
    kind: str = "paragraph"

    def as_dict(self) -> dict:
        return {
            "id": self.index,
            "text": self.text,
            "translate": self.translate,
            "kind": self.kind,
        }


def _has_blank_lines(text: str) -> bool:
    return bool(re.search(r"\n\s*\n", text))


def _line_mode_heuristic(text: str) -> bool:
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 3:
        return False
    short = [line for line in lines if len(line) <= 100]
    return len(short) / len(lines) >= 0.5


def _is_fenced_code(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("```") and stripped.count("```") >= 2


def _sentence_cut(text: str, limit: int) -> list[str]:
    """Split at sentence ends, then hard-split anything still over the limit."""
    if len(text) <= limit:
        return [text]

    pieces: list[str] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        boundary = False
        if ch in _CJK_END:
            boundary = True
        elif ch in ".!?" and (i + 1 >= n or text[i + 1].isspace()):
            boundary = True
        if boundary:
            end = i + 1
            while end < n and text[end] in _CLOSERS:
                end += 1
            if text[start:end].strip():
                pieces.append(text[start:end])
            start = end
            i = end
            continue
        i += 1
    if start < n:
        pieces.append(text[start:])

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > limit:
            if current:
                chunks.append(current)
                current = ""
            for offset in range(0, len(piece), limit):
                chunks.append(piece[offset:offset + limit])
            continue
        if current and len(current) + len(piece) > limit:
            chunks.append(current)
            current = piece
        else:
            current += piece
    if current:
        chunks.append(current)
    return chunks


def _split_preserving(text: str, pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    parts = pattern.split(text)
    # re.split with one capturing group yields [text, sep, text, sep, ...]
    result: list[tuple[str, str]] = []
    for idx in range(0, len(parts), 2):
        content = parts[idx]
        sep = parts[idx + 1] if idx + 1 < len(parts) else ""
        if content or sep:
            result.append((content, sep))
    return result


def split_blocks(text: str, mode: str = "auto",
                 max_chars: int = MAX_BLOCK_CHARS) -> list[Block]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []

    if mode == "auto":
        use_line = (not _has_blank_lines(text)) and _line_mode_heuristic(text)
        effective = "line" if use_line else "paragraph"
    else:
        effective = mode

    pattern = _LINE_SEP if effective == "line" else _PARA_SEP
    pairs = _split_preserving(text, pattern)

    blocks: list[Block] = []
    for content, sep in pairs:
        if not content:
            # Preserve pure separators on the previous block.
            if blocks and sep:
                blocks[-1].sep_after += sep
            continue
        if not content.strip():
            blocks.append(Block(len(blocks), content, sep, translate=False,
                                kind="separator"))
            continue
        fenced = _is_fenced_code(content)
        subchunks = [content] if fenced else _sentence_cut(content, max_chars)
        for idx, chunk in enumerate(subchunks):
            blocks.append(
                Block(
                    index=len(blocks),
                    text=chunk,
                    sep_after=sep if idx == len(subchunks) - 1 else "",
                    translate=not fenced,
                    kind="code" if fenced else effective,
                )
            )
    return blocks


def join_blocks(blocks: list[Block], translations: dict[int, str]) -> str:
    return "".join(translations.get(block.index, block.text) + block.sep_after
                   for block in blocks)
