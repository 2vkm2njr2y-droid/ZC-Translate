from app.backend.pipeline.placeholders import protect
from app.backend.pipeline.postprocess import check_output, clean_output, normalize_punctuation


def test_clean_output_removes_labels_and_special_tokens():
    text = "译文：你好。<|im_end|>"
    assert clean_output(text, "zh") == "你好。"


def test_chinese_punctuation():
    assert normalize_punctuation("你好,世界.再见!", "zh") == "你好，世界。再见！"


def test_japanese_comma():
    assert normalize_punctuation("今日,いい天気。", "ja") == "今日、いい天気。"


def test_english_punctuation():
    assert normalize_punctuation("你好，world。", "en") == "你好, world."


def test_placeholder_and_number_checks():
    protected = protect("版本 1.2 访问 https://example.com 和 `code`")
    source = "版本 1.2 访问 ⟦0⟧ 和 ⟦1⟧"
    target = "版本 1.2 访问 ⟦0⟧ 和 ⟦1⟧"
    checks = check_output(source, target, "zh", protected)
    assert not checks.placeholders_missing
    assert not checks.placeholders_duplicated
    assert not checks.numbers_missing


def test_empty_and_same_warnings():
    protected = protect("hello")
    checks = check_output("hello", "", "zh", protected)
    assert "译文为空" in checks.warnings
    checks = check_output("hello", "hello", "zh", protected)
    assert "译文与原文相同" in checks.warnings
