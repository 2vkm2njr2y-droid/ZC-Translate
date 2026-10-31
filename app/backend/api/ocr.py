from __future__ import annotations

import asyncio
import base64
import binascii
from pathlib import Path

from fastapi import APIRouter, Request

from ..pipeline import langid
from ..schemas import DocumentTranslateRequest, OCRImageRequest, TranslateRequest
from ..services.jobs import QueueFull
from ..services.ocr import (
    OCRUnavailable,
    OfflineOCR,
    translate_docx,
    translate_plain_text,
    translate_scanned_pdf,
)
from .common import error_response, job_stream_response

router = APIRouter(prefix="/api", tags=["ocr"])
_ocr = OfflineOCR()


def _decode(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("文件数据损坏，请重新选择文件。") from exc


def _document_output_name(file_name: str, suffix: str) -> str:
    return f"{Path(file_name).stem}_翻译{suffix}"


def _save_document_output(output: bytes, body: DocumentTranslateRequest,
                          suffix: str) -> tuple[str, str]:
    """Write the translated file beside the source when the desktop path is available."""
    output_name = _document_output_name(body.file_name, suffix)
    saved_path = ""
    if body.source_path:
        source = Path(body.source_path).resolve()
        if source.suffix.lower() == suffix and source.parent.exists():
            target = source.with_name(output_name)
            target.write_bytes(output)
            saved_path = str(target)
    return output_name, saved_path


def _translate_document_content(suffix: str, content: bytes, file_name: str,
                                translator, translate_request: TranslateRequest,
                                *, emit=None, cancel=None) -> tuple[bytes, dict]:
    """Route a document to the existing per-format translation helpers."""
    if suffix in {".txt", ".md"}:
        return translate_plain_text(content, file_name, translator, translate_request)
    if suffix == ".docx":
        return translate_docx(content, file_name, translator, translate_request,
                              emit=emit, cancel=cancel)
    return translate_scanned_pdf(content, file_name, _ocr, translator, translate_request)


def _document_job(body: DocumentTranslateRequest, app, emit, cancel) -> None:
    """Background job used by the streaming document endpoint."""
    suffix = Path(body.file_name).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf", ".docx"}:
        emit("error", {"code": "UNSUPPORTED_FILE",
                       "message": "当前支持纯文本、PDF 和 Word 文档。"})
        return

    output_name = _document_output_name(body.file_name, suffix)
    if cancel.is_set():
        emit("done", {
            "file_name": output_name, "saved_path": "", "content_base64": "",
            "segments": 0, "total": 0, "cancelled": True, "elapsed_ms": 0,
        })
        return

    try:
        content = _decode(body.content_base64)
        translate_request = TranslateRequest(
            text="占位文本", source_lang=body.source_lang, target_lang=body.target_lang,
            profile_id=body.profile_id, device=body.device, glossary_id=body.glossary_id,
            style=body.style, use_tm=body.use_tm,
        )
        emit("status", {"phase": "loading", "message": "正在读取文档…"})
        output, info = _translate_document_content(
            suffix, content, body.file_name, app.state.translator,
            translate_request, emit=emit, cancel=cancel,
        )
        event_info = {key: value for key, value in info.items() if key != "text"}
        if info.get("cancelled"):
            emit("done", {
                **event_info, "file_name": output_name, "saved_path": "",
                "content_base64": "", "cancelled": True,
            })
            return
        saved_path = ""
        if body.source_path:
            _, saved_path = _save_document_output(output, body, suffix)
        encoded = "" if saved_path else base64.b64encode(output).decode("ascii")
        emit("done", {
            **event_info, "file_name": output_name, "saved_path": saved_path,
            "content_base64": encoded, "cancelled": False,
        })
    except OCRUnavailable as exc:
        emit("error", {"code": "OCR_UNAVAILABLE", "message": str(exc)})
    except ValueError as exc:
        emit("error", {"code": "DOCUMENT_INPUT", "message": str(exc)})
    except OSError as exc:
        emit("error", {"code": "DOCUMENT_SAVE_FAILED",
                       "message": f"无法保存翻译文件：{exc}"})
    except Exception as exc:  # noqa: BLE001
        emit("error", {"code": "DOCUMENT_TRANSLATE_FAILED",
                       "message": f"文档翻译失败：{exc}"})


@router.get("/ocr/capabilities")
async def capabilities():
    try:
        try:
            import pymupdf as fitz  # noqa: F401
        except ImportError:
            import fitz  # noqa: F401
        import rapidocr  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:
        return {"available": False, "engine": "RapidOCR", "message": "OCR 组件未安装"}
    return {"available": True, "engine": "RapidOCR + ONNX Runtime", "languages": ["zh", "ja", "en"]}


def _with_language(result: dict) -> dict:
    guess = langid.detect_language(str(result.get("text", "")))
    result["detected_lang"] = guess.lang
    result["language_confidence"] = round(guess.confidence, 2)
    return result


@router.post("/ocr/image")
async def ocr_image(body: OCRImageRequest):
    try:
        content = _decode(body.content_base64)
        result = await asyncio.to_thread(_ocr.image, content, source_name=body.file_name)
        return _with_language(result)
    except OCRUnavailable as exc:
        return error_response(503, "OCR_UNAVAILABLE", str(exc))
    except ValueError as exc:
        return error_response(400, "OCR_INPUT", str(exc))
    except Exception as exc:  # noqa: BLE001
        return error_response(500, "OCR_FAILED", f"识别失败：{exc}")


@router.post("/document/translate/stream")
async def document_translate_stream(body: DocumentTranslateRequest, request: Request):
    app = request.app
    loop = asyncio.get_running_loop()

    def run_job(emit, cancel):
        _document_job(body, app, emit, cancel)

    try:
        job = app.state.jobs.submit("document", run_job, loop)
    except QueueFull as exc:
        return error_response(429, "QUEUE_FULL", str(exc))

    return job_stream_response(job, request)


@router.post("/document/translate")
async def document_translate(body: DocumentTranslateRequest, request: Request):
    suffix = Path(body.file_name).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf", ".docx"}:
        return error_response(400, "UNSUPPORTED_FILE", "当前支持纯文本、PDF 和 Word 文档。")
    try:
        content = _decode(body.content_base64)
        translate_request = TranslateRequest(
            text="占位文本", source_lang=body.source_lang, target_lang=body.target_lang,
            profile_id=body.profile_id, device=body.device, glossary_id=body.glossary_id,
            style=body.style, use_tm=body.use_tm,
        )
        translator = request.app.state.translator
        output, info = await asyncio.to_thread(
            _translate_document_content, suffix, content, body.file_name,
            translator, translate_request,
        )
        output_name, saved_path = _save_document_output(output, body, suffix)
        # The desktop app saves the returned bytes beside the original file;
        # the browser fallback receives a normal download response instead.
        encoded = base64.b64encode(output).decode("ascii")
        return {"file_name": output_name, "content_base64": encoded,
                "saved_path": saved_path, **info}
    except OCRUnavailable as exc:
        return error_response(503, "OCR_UNAVAILABLE", str(exc))
    except ValueError as exc:
        return error_response(400, "DOCUMENT_INPUT", str(exc))
    except Exception as exc:  # noqa: BLE001
        return error_response(500, "DOCUMENT_TRANSLATE_FAILED", f"文档翻译失败：{exc}")
