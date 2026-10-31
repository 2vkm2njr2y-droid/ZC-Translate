"""Output cleanup, target-language punctuation and automatic sanity checks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .placeholders import PLACEHOLDER_RE, ProtectedText

_SPECIAL_TOKEN = re.compile(r"<\|(?:im_start|im_end|endoftext|eot_id|startoftext)\|>")
_LABEL = re.compile(
    r"^\s*(?:译文|翻译结果|翻译|Translation|Translated text|Output)\s*[:：]\s*",
    re.IGNORECASE,
)
_PROMPT_ECHO = re.compile(
    r"^\s*(?:将以下文本翻译为|请将以下文本翻译为|Translate the following text into|"
    r"Please translate the following text into).*$",
    re.IGNORECASE | re.MULTILINE,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
_URL = re.compile(r"https?://[^\s<>\"'）)】]+")


@dataclass
class OutputChecks:
    warnings: list[str]
    numbers_missing: list[str]
    urls_missing: list[str]
    placeholders_missing: list[int]
    placeholders_duplicated: list[int]


def clean_output(text: str, target_lang: str) -> str:
    text = text.replace("\u0000", "")
    text = _SPECIAL_TOKEN.sub("", text)
    text = _PROMPT_ECHO.sub("", text)
    text = _LABEL.sub("", text)
    text = text.strip()
    text = normalize_punctuation(text, target_lang)
    return text.strip()


def _cjk(ch: str) -> bool:
    return bool(re.match(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", ch))


def normalize_punctuation(text: str, target_lang: str) -> str:
    if target_lang in {"zh", "ja"}:
        # ASCII punctuation adjacent to CJK becomes the target's full-width form.
        text = re.sub(r"(?<=[\u3400-\u9fff])\s*,\s*", "，" if target_lang == "zh" else "、", text)
        text = re.sub(r"(?<=[\u3400-\u9fff])\s*;\s*", "；", text)
        text = re.sub(r"(?<=[\u3400-\u9fff])\s*:\s*", "：", text)
        text = re.sub(r"(?<=[\u3400-\u9fff])\s*!\s*", "！", text)
        text = re.sub(r"(?<=[\u3400-\u9fff])\s*\?\s*", "？", text)
        text = re.sub(r"(?<=[\u3400-\u9fff])\.(?=[\u3400-\u9fff]|\s|$)", "。", text)
        # Remove spaces between CJK characters.
        text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    else:
        text = re.sub(r"(?<=[A-Za-z0-9])\s+([,.;:!?])", r"\1", text)
        text = text.replace("，", ", ").replace("。", ". ").replace("！", "! ").replace("？", "? ")
        text = text.replace("；", "; ").replace("：", ": ")
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
        text = text.strip()
    return text


def check_output(source: str, target: str, target_lang: str,
                 protected: ProtectedText) -> OutputChecks:
    warnings: list[str] = []
    numbers_missing: list[str] = []
    urls_missing: list[str] = []

    if not target.strip():
        warnings.append("译文为空")
    if source.strip() == target.strip():
        warnings.append("译文与原文相同")
    src_len = len(source.strip())
    tgt_len = len(target.strip())
    if src_len >= 20 and tgt_len < max(8, int(src_len * 0.2)):
        warnings.append("译文明显偏短，可能有漏译")
    if src_len >= 20 and tgt_len > int(src_len * 3.5):
        warnings.append("译文明显偏长，可能有重复或解释性内容")

    source_numbers = _NUMBER.findall(source)
    for number in source_numbers:
        if number not in target:
            numbers_missing.append(number)
    if numbers_missing:
        warnings.append("数字/单位可能未保留：" + "、".join(numbers_missing[:5]))

    source_urls = _URL.findall(source)
    for url in source_urls:
        if url not in target and url not in protected.mapping.values():
            urls_missing.append(url)
    if urls_missing:
        warnings.append("URL 可能未保留")

    missing = protected.missing_keys(target)
    duplicated = protected.duplicated_keys(target)
    if missing:
        warnings.append("占位符缺失：" + "、".join(f"⟦{idx}⟧" for idx in missing[:5]))
    if duplicated:
        warnings.append("占位符重复：" + "、".join(f"⟦{idx}⟧" for idx in duplicated[:5]))

    # A cheap repetition detector: the same 12-char window three times in a row.
    if len(target) > 60:
        for start in range(0, min(len(target) - 36, 200)):
            window = target[start:start + 12]
            if window.strip() and target[start:start + 36] == window * 3:
                warnings.append("译文出现重复片段")
                break

    return OutputChecks(
        warnings=warnings,
        numbers_missing=numbers_missing,
        urls_missing=urls_missing,
        placeholders_missing=missing,
        placeholders_duplicated=duplicated,
    )


def has_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text))
