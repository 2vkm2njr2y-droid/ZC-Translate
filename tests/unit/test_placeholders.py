from app.backend.pipeline.placeholders import PLACEHOLDER_RE, instruction, protect


def test_roundtrip_protects_urls_code_and_templates():
    text = "打开 https://example.com/a?b=1 并设置 {user_name}，命令是 `npm run dev`。"
    protected = protect(text)
    assert protected.count >= 3
    assert "https://" not in protected.masked
    assert PLACEHOLDER_RE.search(protected.masked)
    assert protected.restore(protected.masked) == text


def test_missing_and_duplicate_detection():
    protected = protect("访问 https://example.com 和 `code`")
    assert protected.missing_keys("⟦0⟧ ⟦0⟧") == [1]
    assert protected.duplicated_keys("⟦0⟧ ⟦0⟧ ⟦1⟧") == [0]


def test_instruction_mentions_tokens():
    protected = protect("https://a.example x")
    chinese = instruction(protected.mapping, True)
    english = instruction(protected.mapping, False)
    assert "⟦0⟧" in chinese
    assert "placeholder" in english


def test_restore_keeps_unknown_tokens():
    protected = protect("https://a.example")
    assert protected.restore("结果 ⟦0⟧ 和 ⟦9⟧") == "结果 https://a.example 和 ⟦9⟧"
