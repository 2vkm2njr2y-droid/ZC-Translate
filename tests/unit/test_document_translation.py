from __future__ import annotations

import io
from types import SimpleNamespace

from docx import Document

from app.backend.services.ocr import translate_docx, translate_plain_text


class FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, request, emit, cancel):
        self.calls.append(request.text)
        emit("done", {"text": f"译:{request.text}"})


class CancelAfterFirstTranslator(FakeTranslator):
    def run(self, request, emit, cancel):
        super().run(request, emit, cancel)
        cancel.set()


class FakeRequest:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.target_lang = "zh"

    def model_copy(self, *, update):
        return SimpleNamespace(text=update["text"], target_lang=self.target_lang)


def _docx(*paragraphs: str, table: bool = False) -> bytes:
    source = io.BytesIO()
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        document.add_table(rows=1, cols=1).cell(0, 0).text = "world"
    document.save(source)
    return source.getvalue()


def test_plain_text_translation_preserves_blank_lines_and_line_endings():
    output, info = translate_plain_text(
        b"hello\r\n\r\nworld\n",
        "notes.txt",
        FakeTranslator(),
        FakeRequest(),
    )

    assert output.decode("utf-8") == "译:hello\r\n\r\n译:world\n"
    assert info["segments"] == 2


def test_docx_translation_keeps_a_new_file_payload():
    output, info = translate_docx(
        _docx("hello", table=True), "report.docx", FakeTranslator(), FakeRequest()
    )
    translated = Document(io.BytesIO(output))

    assert translated.paragraphs[0].text == "译:hello"
    assert translated.tables[0].cell(0, 0).text == "译:world"
    assert info["segments"] == 2
    assert info["total"] == 2
    assert info["cancelled"] is False


def test_docx_translation_emits_progress_and_reuses_duplicates():
    translator = FakeTranslator()
    events: list[tuple[str, dict]] = []

    output, info = translate_docx(
        _docx("hello", "hello", "world"),
        "duplicates.docx",
        translator,
        FakeRequest(),
        emit=lambda event, data=None: events.append((event, data or {})),
    )
    translated = Document(io.BytesIO(output))

    assert [paragraph.text for paragraph in translated.paragraphs] == [
        "译:hello", "译:hello", "译:world",
    ]
    assert translator.calls == ["hello", "world"]
    assert info["segments"] == 3
    assert info["total"] == 3
    meta = next(data for event, data in events if event == "meta")
    assert meta["total"] == 3
    assert meta["chars"] == 15
    progress = [data for event, data in events if event == "progress"]
    assert [item["done"] for item in progress] == [1, 2, 3]
    assert progress[-1]["percent"] == 100.0


def test_docx_translation_cancel_stops_without_file():
    translator = CancelAfterFirstTranslator()
    events: list[tuple[str, dict]] = []

    output, info = translate_docx(
        _docx("hello", "world"),
        "cancel.docx",
        translator,
        FakeRequest(),
        emit=lambda event, data=None: events.append((event, data or {})),
    )

    assert output == b""
    assert translator.calls == ["hello"]
    assert info["cancelled"] is True
    assert info["segments"] == 1
    assert info["total"] == 2
    assert [data for event, data in events if event == "progress"][-1]["done"] == 1


def test_docx_translation_skips_empty_paragraphs():
    translator = FakeTranslator()

    output, info = translate_docx(
        _docx("", "hello", ""),
        "empty.docx",
        translator,
        FakeRequest(),
    )
    translated = Document(io.BytesIO(output))

    assert [paragraph.text for paragraph in translated.paragraphs] == ["", "译:hello", ""]
    assert translator.calls == ["hello"]
    assert info["total"] == 1
    assert info["segments"] == 1
