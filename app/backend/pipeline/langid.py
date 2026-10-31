"""Deterministic language detection for Chinese, Japanese and English.

Only the three languages exposed by the product are detected.  The detector is
script based: Japanese uses kana, Chinese uses Han without kana, English uses
Latin letters.  Mixed Chinese/Japanese text is resolved by the kana ratio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_LATIN = re.compile(r"[A-Za-z\u00c0-\u024f]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")


@dataclass(frozen=True)
class LanguageGuess:
    lang: str | None
    confidence: float
    reason: str


def detect_language(text: str) -> LanguageGuess:
    if not text or not text.strip():
        return LanguageGuess(None, 0.0, "empty")
    han = len(_HAN.findall(text))
    kana = len(_KANA.findall(text))
    latin = len(_LATIN.findall(text))
    hangul = len(_HANGUL.findall(text))
    cyrillic = len(_CYRILLIC.findall(text))

    if kana and kana / max(1, han + kana) >= 0.01:
        return LanguageGuess("ja", 0.98, "kana")
    if han and han >= max(2, int(latin * 0.2)):
        confidence = 0.9 if han >= 4 else 0.6
        return LanguageGuess("zh", confidence, "han")
    if latin and latin >= max(2, han):
        return LanguageGuess("en", 0.95, "latin")
    if kana:
        return LanguageGuess("ja", 0.6, "kana-minority")
    if han:
        return LanguageGuess("zh", 0.5, "han-minority")
    if hangul or cyrillic:
        return LanguageGuess(None, 0.0, "unsupported-script")
    return LanguageGuess(None, 0.0, "unknown")


def language_label(lang: str | None) -> str:
    return {"zh": "中文", "ja": "日语", "en": "英语"}.get(lang or "", "未知")
