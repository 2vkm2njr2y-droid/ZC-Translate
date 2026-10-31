from app.backend.pipeline.splitter import join_blocks, split_blocks


def test_paragraph_separators_are_preserved():
    text = "第一段。\n\n第二段。\n\n\n第三段。"
    blocks = split_blocks(text)
    assert [block.text for block in blocks] == ["第一段。", "第二段。", "第三段。"]
    translated = {block.index: f"T{block.index}" for block in blocks}
    joined = join_blocks(blocks, translated)
    assert joined == "T0\n\nT1\n\n\nT2"


def test_line_mode_for_short_lines():
    text = "Open file\nSave file\nClose window"
    blocks = split_blocks(text)
    assert len(blocks) == 3
    assert all(block.kind == "line" for block in blocks)


def test_many_short_lines_are_coalesced():
    text = "\n".join(f"line {index}" for index in range(200))
    blocks = split_blocks(text)
    assert len(blocks) <= 40
    assert join_blocks(blocks, {block.index: block.text for block in blocks}) == text


def test_coalescing_keeps_fenced_code_out_of_translation():
    lines = "\n".join(f"line {index}" for index in range(100))
    text = f"{lines}\n\n```\ncode\n```\n\n{lines}"
    blocks = split_blocks(text)
    assert len([block for block in blocks if block.translate]) <= 40
    code = [block for block in blocks if not block.translate]
    assert len(code) == 1
    assert "code" in code[0].text


def test_long_text_is_split_and_rejoined():
    text = "这是第一句。" * 400
    blocks = split_blocks(text, max_chars=100)
    assert len(blocks) > 1
    assert "".join(block.text + block.sep_after for block in blocks) == text


def test_fenced_code_is_not_translated():
    text = "说明文字。\n\n```python\nprint('hello')\n```\n\n结束。"
    blocks = split_blocks(text)
    code = [block for block in blocks if not block.translate]
    assert len(code) == 1
    assert "print" in code[0].text


def test_blank_lines_only():
    assert split_blocks("   \n\n") == [] or all(not b.translate for b in split_blocks("   \n\n"))
