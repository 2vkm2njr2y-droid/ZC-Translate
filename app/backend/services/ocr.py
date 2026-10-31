"""Offline OCR and scanned-PDF translation helpers.

The heavy OCR/PDF packages are optional at import time so the text translator
can still start and show a clear diagnostic when the OCR bundle is missing.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class OCRUnavailable(RuntimeError):
    """Raised when the optional offline OCR bundle is not installed."""


def _translate_segment(text: str, translator: Any, request: Any) -> str:
    """Translate one document segment and return the completed text."""
    events: list[tuple[str, dict[str, Any]]] = []

    def collect(event: str, data: dict[str, Any] | None = None) -> None:
        events.append((event, data or {}))

    translator.run(request.model_copy(update={"text": text}), collect, threading.Event())
    done = next((data for event, data in reversed(events) if event == "done"), None)
    if done is None:
        error = next((data for event, data in reversed(events) if event == "error"), None)
        raise RuntimeError((error or {}).get("message", "文档文本翻译失败"))
    return str(done.get("text", "")).strip() or text


def _translated_text_parts(text: str, translator: Any, request: Any) -> str:
    """Translate non-empty lines while preserving the original line layout."""
    parts = text.splitlines(keepends=True)
    output: list[str] = []
    for part in parts:
        line = part.rstrip("\r\n")
        ending = part[len(line):]
        output.append(_translate_segment(line, translator, request) + ending if line.strip() else part)
    return "".join(output)


def translate_plain_text(content: bytes, file_name: str, translator: Any,
                        request: Any) -> tuple[bytes, dict[str, Any]]:
    """Translate UTF text and preserve line endings for txt/md files."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("gb18030")
    translated = _translated_text_parts(text, translator, request)
    return translated.encode("utf-8"), {"text": translated, "segments": len([line for line in text.splitlines() if line.strip()])}


def _translate_segment_with_meta(text: str, translator: Any, request: Any,
                                cancel: threading.Event | None = None
                                ) -> tuple[str, dict[str, Any]]:
    """Translate one document segment and return the terminal event metadata."""
    done: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def collect(event: str, data: dict[str, Any] | None = None) -> None:
        nonlocal done, error
        if event == "done":
            done = data or {}
        elif event == "error":
            error = data or {}

    translator.run(request.model_copy(update={"text": text}), collect,
                   cancel or threading.Event())
    if done is None:
        if cancel is not None and cancel.is_set():
            return text, {"cancelled": True, "text": text}
        raise RuntimeError((error or {}).get("message", "文档文本翻译失败"))
    target = str(done.get("text", "")).strip() or text
    return target, done


def _collect_docx_paragraphs(document: Any) -> list[tuple[Any, str]]:
    """Return non-empty body and table paragraphs in the existing traversal order."""
    items: list[tuple[Any, str]] = []

    def add(paragraph: Any) -> None:
        source = str(paragraph.text or "").strip()
        if source:
            items.append((paragraph, source))

    def walk(table: Any) -> None:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    add(paragraph)
                for nested in cell.tables:
                    walk(nested)

    for paragraph in document.paragraphs:
        add(paragraph)
    for table in document.tables:
        walk(table)
    return items


def _apply_docx_translation(paragraph: Any, target: str) -> None:
    """Write the translation into the first run, keeping the existing formatting rule."""
    runs = list(paragraph.runs)
    if runs:
        runs[0].text = target
        for run in runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(target)


def translate_docx(content: bytes, file_name: str, translator: Any, request: Any,
                   *, emit: Callable[[str, dict[str, Any] | None], None] | None = None,
                   cancel: threading.Event | None = None
                   ) -> tuple[bytes, dict[str, Any]]:
    """Translate DOCX paragraphs and table cells while keeping the document file.

    ``emit`` receives document-level ``meta``/``progress`` events.  When ``cancel``
    is set, processed paragraphs are kept in memory for translation memory, but no
    output file is produced.
    """
    try:
        from docx import Document  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional install
        raise OCRUnavailable("Word 文档支持未安装，请安装 python-docx。") from exc

    try:
        document = Document(io.BytesIO(content))
    except Exception as exc:
        raise ValueError(f"无法打开 Word 文档：{file_name}") from exc

    notify = emit or (lambda event, data=None: None)
    stop = cancel or threading.Event()
    items = _collect_docx_paragraphs(document)
    total = len(items)
    chars_total = sum(len(source) for _, source in items)
    notify("meta", {
        "file_name": file_name,
        "total": total,
        "chars": chars_total,
        "target_lang": request.target_lang,
    })
    notify("status", {"phase": "loading", "message": "正在准备模型…"})

    started = time.perf_counter()
    cache: dict[str, str] = {}
    translated: dict[int, str] = {}
    chars_done = 0
    cancelled = stop.is_set()

    if not cancelled:
        for index, (paragraph, source) in enumerate(items):
            if stop.is_set():
                cancelled = True
                break
            if source in cache:
                target = cache[source]
            else:
                target, done = _translate_segment_with_meta(
                    source, translator, request, stop,
                )
                if done.get("cancelled"):
                    cancelled = True
                    break
                cache[source] = target
            _apply_docx_translation(paragraph, target)
            translated[index] = target
            chars_done += len(source)
            notify("progress", {
                "done": len(translated),
                "total": total,
                "percent": round(len(translated) * 100 / total, 1) if total else 0.0,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "chars_done": chars_done,
                "chars_total": chars_total,
            })

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if cancelled:
        return b"", {
            "text": "",
            "segments": len(translated),
            "total": total,
            "chars": chars_total,
            "cancelled": True,
            "elapsed_ms": elapsed_ms,
        }

    output = io.BytesIO()
    document.save(output)
    return output.getvalue(), {
        "text": "",
        "segments": total,
        "total": total,
        "chars": chars_total,
        "cancelled": False,
        "elapsed_ms": elapsed_ms,
    }


def _optional_imports():
    try:
        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            import fitz  # type: ignore
        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore
        from rapidocr import RapidOCR  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local install
        raise OCRUnavailable(
            "OCR 组件未安装。请运行 scripts\\setup_ocr.ps1 安装 RapidOCR、"
            "ONNX Runtime、Pillow 和 PyMuPDF。"
        ) from exc
    return fitz, np, Image, RapidOCR


class OfflineOCR:
    def __init__(self) -> None:
        self._engine: Any | None = None

    def _get_engine(self):
        _fitz, _np, _image, RapidOCR = _optional_imports()
        if self._engine is None:
            self._engine = RapidOCR()
        return self._engine

    def image(self, content: bytes, *, source_name: str = "image") -> dict[str, Any]:
        _fitz, np, Image, _RapidOCR = _optional_imports()
        try:
            image = Image.open(io.BytesIO(content)).convert("RGB")
        except Exception as exc:
            raise ValueError(f"无法读取图片：{source_name}") from exc
        result = self._get_engine()(np.asarray(image))
        return self._normalise_result(result, image.width, image.height, source_name)

    def pdf(self, content: bytes, *, source_name: str = "document.pdf") -> dict[str, Any]:
        fitz, _np, _Image, _RapidOCR = _optional_imports()
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"无法打开 PDF：{source_name}") from exc
        pages: list[dict[str, Any]] = []
        for page_index, page in enumerate(document):
            scale = 2.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            page_result = self.image(pixmap.tobytes("png"), source_name=f"{source_name} 第{page_index + 1}页")
            # Store PDF points as well as pixel coordinates for the layout pass.
            for item in page_result["items"]:
                item["bbox_pdf"] = [round(value / scale, 2) for value in item["bbox"]]
            pages.append({
                "page": page_index + 1,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
                "text": page_result["text"],
                "items": page_result["items"],
            })
        document.close()
        return {"file_name": source_name, "pages": pages,
                "text": "\n\n".join(page["text"] for page in pages)}

    @staticmethod
    def _normalise_result(result: Any, width: int, height: int, source_name: str) -> dict[str, Any]:
        # RapidOCR 3.x returns an OCRResult object; older releases return a
        # tuple. Supporting both keeps portable builds compatible.
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None and isinstance(result, (tuple, list)) and result:
            boxes = result[0]
            texts = result[1] if len(result) > 1 else []
            scores = result[2] if len(result) > 2 else []
        if boxes is None:
            boxes = []
        if texts is None:
            texts = []
        if scores is None:
            scores = []
        items: list[dict[str, Any]] = []
        for index, raw_box in enumerate(boxes):
            points = [[float(point[0]), float(point[1])] for point in raw_box]
            if not points:
                continue
            x0 = max(0.0, min(point[0] for point in points))
            y0 = max(0.0, min(point[1] for point in points))
            x1 = min(float(width), max(point[0] for point in points))
            y1 = min(float(height), max(point[1] for point in points))
            text = str(texts[index]).strip() if index < len(texts) else ""
            if not text:
                continue
            score = float(scores[index]) if index < len(scores) else 0.0
            items.append({"text": text, "score": round(score, 4),
                          "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]})
        items.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
        return {"file_name": source_name, "width": width, "height": height,
                "text": "\n".join(item["text"] for item in items), "items": items}


def translate_scanned_pdf(content: bytes, file_name: str, ocr: OfflineOCR,
                          translator: Any, request: Any) -> tuple[bytes, dict[str, Any]]:
    """OCR each page, translate every detected line, and paint it over the scan."""
    fitz, _np, _Image, _RapidOCR = _optional_imports()
    scan = ocr.pdf(content, source_name=file_name)
    document = fitz.open(stream=content, filetype="pdf")
    translated_pages: list[str] = []
    for page_data, page in zip(scan["pages"], document, strict=False):
        for item in page_data["items"]:
            source = item["text"]
            events: list[tuple[str, dict[str, Any]]] = []
            def collect(event: str, data: dict[str, Any] | None = None,
                        bucket=events) -> None:
                bucket.append((event, data or {}))

            translator.run(request.model_copy(update={"text": source}), collect, threading.Event())
            done = next((data for event, data in reversed(events) if event == "done"), None)
            if not done:
                error = next((data for event, data in reversed(events) if event == "error"), None)
                raise RuntimeError((error or {}).get("message", "PDF 文本翻译失败"))
            target = str(done.get("text", "")).strip() or source
            translated_pages.append(target)
            x0, y0, x1, y1 = item["bbox_pdf"]
            rect = fitz.Rect(x0, y0, x1, y1)
            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
            size = max(5.0, min(22.0, (y1 - y0) * 0.72))
            page.insert_textbox(rect, target, fontsize=size, fontname="china-s",
                                color=(0, 0, 0), overlay=True, align=0)
    output = io.BytesIO()
    document.save(output, garbage=4, deflate=True)
    document.close()
    return output.getvalue(), {"pages": len(scan["pages"]),
                               "text": "\n".join(translated_pages)}

