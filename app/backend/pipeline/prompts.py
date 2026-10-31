"""Official Hy-MT2 prompt construction.

The model card explicitly states there is no default system prompt and all
instructions must be placed in the user message.  Language names must be full
names; Chinese prompts are used whenever Chinese is the source or target.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import STYLE_PROMPTS
from .glossary import SelectedTerm
from .placeholders import instruction as placeholder_instruction

LANGUAGE_NAMES_ZH = {"zh": "中文", "ja": "日语", "en": "英语"}
LANGUAGE_NAMES_EN = {"zh": "Chinese", "ja": "Japanese", "en": "English"}

STYLE_NAMES_EN = {
    "formal": "formal and rigorous written language",
    "casual": "natural, conversational expression",
    "technical": "accurate and concise technical documentation style",
    "literary": "literary style that preserves the tone and imagery of the source",
}

DEFAULT_ZH = "将以下文本翻译为{target}，注意只需要输出翻译后的结果，不要额外解释："
DEFAULT_EN = ("Translate the following text into {target}. Note that you should only "
              "output the translated result without any additional explanation:")
STYLE_ZH = "请将以下文本翻译为{target}。\n注意翻译的风格要严格符合【{style}】"
STYLE_EN = ("Please translate the following text into {target}. Note that the translation "
            "style must strictly conform to [{style}]:")
TERM_ZH = "参考下面的翻译：\n"
TERM_EN = "Reference the following translations:\n"


@dataclass(frozen=True)
class BuiltPrompt:
    text: str
    chinese: bool
    target_name: str

    def messages(self) -> list[dict[str, str]]:
        # No system message: required by the Hy-MT2 model card.
        return [{"role": "user", "content": self.text}]


def use_chinese_prompt(src_lang: str | None, tgt_lang: str) -> bool:
    return src_lang == "zh" or tgt_lang == "zh"


def target_language_name(tgt_lang: str, chinese: bool) -> str:
    return (LANGUAGE_NAMES_ZH if chinese else LANGUAGE_NAMES_EN)[tgt_lang]


def build_prompt(
    *,
    text: str,
    src_lang: str | None,
    tgt_lang: str,
    terms: list[SelectedTerm] | None = None,
    style: str = "default",
    placeholder_count: int = 0,
    background: str = "",
) -> BuiltPrompt:
    chinese = use_chinese_prompt(src_lang, tgt_lang)
    target = target_language_name(tgt_lang, chinese)
    terms = terms or []

    parts: list[str] = []
    if terms:
        lines = [TERM_ZH if chinese else TERM_EN]
        for term in terms:
            if chinese:
                lines.append(f"{term.source} 翻译成 {term.target}\n")
            else:
                lines.append(f"{term.source} translates to {term.target}\n")
        parts.append("".join(lines).rstrip() + "\n")

    style_text = STYLE_PROMPTS.get(style)
    if background:
        if chinese:
            instruction = f"【背景信息】\n{background}\n\n请结合背景信息将以下文本翻译为{target}。"
            if style_text:
                instruction += f"\n注意翻译的风格要严格符合【{style_text}】"
            instruction += "\n注意只需要输出翻译后的结果，不要额外解释："
        else:
            instruction = ("[Background Information]\n"
                            f"{background}\n\nPlease translate the following text into {target}, "
                            "taking the provided background information into consideration.")
            if style_text:
                instruction += (f"\nNote that the translation style must strictly conform to "
                                f"[{STYLE_NAMES_EN.get(style, style_text)}].")
            instruction += "\nNote that you should only output the translated result without any additional explanation:"
    elif style_text:
        if chinese:
            instruction = STYLE_ZH.format(target=target, style=style_text)
        else:
            instruction = STYLE_EN.format(target=target,
                                          style=STYLE_NAMES_EN.get(style, style_text))
    else:
        instruction = DEFAULT_ZH.format(target=target) if chinese else DEFAULT_EN.format(target=target)

    if placeholder_count:
        instruction += "\n" + placeholder_instruction(
            {idx: "" for idx in range(placeholder_count)}, chinese
        )

    parts.append(instruction)
    parts.append("\n\n" + text)
    return BuiltPrompt(text="".join(parts).strip("\n"), chinese=chinese,
                       target_name=target)
