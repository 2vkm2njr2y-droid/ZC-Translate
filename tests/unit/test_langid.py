from app.backend.pipeline.langid import detect_language


def test_chinese():
    guess = detect_language("今天天气真好，我们下午去公园散步吧。")
    assert guess.lang == "zh"


def test_japanese():
    guess = detect_language("今日はとても良い天気ですね。")
    assert guess.lang == "ja"


def test_english():
    guess = detect_language("The update fixes a crash when the cache is missing.")
    assert guess.lang == "en"


def test_mixed_chinese_with_english():
    assert detect_language("这是 API 文档，请更新 cache 目录。").lang == "zh"


def test_japanese_with_kanji_only_is_best_effort():
    # Without kana there is no reliable way to distinguish kanji-only Japanese
    # from Chinese; the UI allows a manual override.
    assert detect_language("日本語").lang == "zh"


def test_empty_and_unsupported():
    assert detect_language("") .lang is None
    assert detect_language("12345 !!!").lang is None
    assert detect_language("안녕하세요").lang is None
