"""Glossary matching, prompt reference formatting and output verification."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class GlossaryTerm:
    source: str
    target: str
    case_sensitive: bool = False
    note: str = ""


@dataclass(frozen=True)
class SelectedTerm:
    source: str
    target: str
    start: int
    end: int


_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")


def _is_cjk(text: str) -> bool:
    return bool(_CJK.search(text))


def _normalize(text: str, casefold: bool = True) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.casefold() if casefold else normalized


def _spans(text: str, term: GlossaryTerm) -> list[tuple[int, int]]:
    source = term.source.strip()
    if not source:
        return []
    if _is_cjk(source):
        spans: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = text.find(source, start)
            if idx < 0:
                break
            spans.append((idx, idx + len(source)))
            start = idx + len(source)
        return spans
    flags = 0 if term.case_sensitive else re.IGNORECASE
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])", flags)
    return [match.span() for match in pattern.finditer(text)]


def select_terms(text: str, terms: Iterable[GlossaryTerm],
                 max_terms: int = 20) -> list[SelectedTerm]:
    candidates: list[SelectedTerm] = []
    for term in terms:
        for start, end in _spans(text, term):
            candidates.append(SelectedTerm(term.source, term.target, start, end))

    # Longest match wins; avoid overlapping spans.
    candidates.sort(key=lambda item: (item.start, -(item.end - item.start)))
    chosen: list[SelectedTerm] = []
    occupied: list[tuple[int, int]] = []
    for candidate in candidates:
        if any(candidate.start < end and candidate.end > start for start, end in occupied):
            continue
        occupied.append((candidate.start, candidate.end))
        chosen.append(candidate)
        if len(chosen) >= max_terms:
            break
    chosen.sort(key=lambda item: item.start)
    return chosen


def glossary_hash(terms: Iterable[GlossaryTerm], glossary_id: str = "") -> str:
    ordered = sorted({(term.source, term.target, term.case_sensitive) for term in terms})
    payload = glossary_id + "\x1f" + "\x1e".join(
        f"{source}\x1d{target}\x1d{int(case_sensitive)}"
        for source, target, case_sensitive in ordered
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def verify_terms(target_text: str, terms: Iterable[SelectedTerm]) -> list[str]:
    normalized_target = _normalize(target_text)
    misses: list[str] = []
    for term in terms:
        expected = _normalize(term.target)
        if expected and expected not in normalized_target:
            misses.append(f"{term.source} → {term.target}")
    return misses
