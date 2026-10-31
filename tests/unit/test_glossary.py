from app.backend.pipeline.glossary import (
    GlossaryTerm,
    glossary_hash,
    select_terms,
    verify_terms,
)


def test_case_insensitive_english_match():
    terms = [GlossaryTerm("cache", "缓存")]
    selected = select_terms("Clear the Cache directory.", terms)
    assert [(term.source, term.target) for term in selected] == [("cache", "缓存")]


def test_case_sensitive_match():
    terms = [GlossaryTerm("API", "接口", case_sensitive=True)]
    selected = select_terms("api and API", terms)
    assert len(selected) == 1
    assert selected[0].start == 8


def test_cjk_substring_and_longest_match():
    terms = [GlossaryTerm("机器", "machine"), GlossaryTerm("机器翻译", "machine translation")]
    selected = select_terms("机器翻译很好用", terms)
    # The longest match wins and the shorter overlapping term is excluded.
    assert len(selected) == 1
    assert selected[0].source == "机器翻译"


def test_no_match_inside_english_word():
    terms = [GlossaryTerm("cat", "猫")]
    assert select_terms("concatenate", terms) == []


def test_verify_terms():
    terms = [GlossaryTerm("cache", "缓存")]
    selected = select_terms("cache", terms)
    assert verify_terms("清理缓存目录", selected) == []
    assert verify_terms("清理目录", selected) == ["cache → 缓存"]


def test_hash_is_stable_and_order_independent():
    a = [GlossaryTerm("a", "甲"), GlossaryTerm("b", "乙")]
    b = list(reversed(a))
    assert glossary_hash(a, "g1") == glossary_hash(b, "g1")
    assert glossary_hash(a, "g1") != glossary_hash(a, "g2")
