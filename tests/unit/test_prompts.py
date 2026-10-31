from app.backend.pipeline.glossary import SelectedTerm
from app.backend.pipeline.prompts import build_prompt


def test_default_chinese_prompt_matches_model_card():
    built = build_prompt(text="今天天气真好。", src_lang="zh", tgt_lang="ja")
    assert built.chinese is True
    assert built.text.startswith("将以下文本翻译为日语")
    assert "只需要输出翻译后的结果，不要额外解释" in built.text
    assert built.text.endswith("今天天气真好。")
    messages = built.messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_english_prompt_for_english_to_japanese():
    built = build_prompt(text="Hello.", src_lang="en", tgt_lang="ja")
    assert built.chinese is False
    assert built.text.startswith("Translate the following text into Japanese")
    assert built.target_name == "Japanese"


def test_terminology_reference_is_before_instruction():
    terms = [SelectedTerm("cache", "缓存", 0, 5)]
    built = build_prompt(text="cache 目录", src_lang="en", tgt_lang="zh", terms=terms)
    assert built.text.index("cache 翻译成 缓存") < built.text.index("将以下文本翻译为中文")


def test_style_and_placeholder_instruction():
    built = build_prompt(
        text="Hello.", src_lang="en", tgt_lang="zh",
        style="formal", placeholder_count=2,
    )
    assert "风格" in built.text
    assert "⟦0⟧" in built.text
    assert "⟦1⟧" in built.text


def test_background_is_used():
    built = build_prompt(
        text="Continue.", src_lang="en", tgt_lang="zh",
        background="Previous source: A\nPrevious translation: 甲",
    )
    assert "【背景信息】" in built.text
    assert "Previous source" in built.text
