"""Batch manga image translation for local Comic-Player integration.

The desktop UI remains separate from this service.  Comic-Player starts ZC in
``--no-window`` mode and receives progress through the normal SSE job queue.
Original images are never overwritten; a manifest makes completed pages
resumable across application restarts.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..schemas import ComicTranslateRequest, ScreenshotTranslateRequest
from .ocr import OCRUnavailable, OfflineOCR, _optional_imports

logger = logging.getLogger(__name__)
Emit = Callable[[str, dict[str, Any] | None], None]


def _file_key(path: Path, request: ComicTranslateRequest) -> str:
    stat = path.stat()
    raw = "|".join([
        str(path.resolve()),
        str(stat.st_size),
        str(stat.st_mtime_ns),
        request.source_lang,
        request.target_lang,
        request.quality,
        request.profile_id or "",
        request.device,
        request.glossary_id or "",
        request.style,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _font_candidates() -> list[Path]:
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return [
        windows / "msyh.ttc",
        windows / "msyhbd.ttc",
        windows / "meiryo.ttc",
        windows / "YuGothM.ttc",
        Path(__file__).resolve().parents[3] / "assets" / "NotoSansCJK-Regular.ttc",
    ]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _font_candidates():
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), max(8, int(size)))
            except OSError:
                continue
    return ImageFont.load_default()


def _fit_font(text: str, box_width: float, box_height: float, vertical: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if not text:
        return _font(12)
    max_size = max(10, int(min(box_height * 0.82, box_width * 0.82)))
    min_size = 9
    for size in range(max_size, min_size - 1, -1):
        candidate = _font(size)
        probe = Image.new("RGB", (4, 4))
        draw = ImageDraw.Draw(probe)
        if vertical:
            widths = [draw.textbbox((0, 0), char, font=candidate)[2] for char in text]
            height = sum(draw.textbbox((0, 0), char, font=candidate)[3] for char in text)
            width = max(widths or [0])
        else:
            left, top, right, bottom = draw.multiline_textbbox((0, 0), text, font=candidate, spacing=1)
            width, height = right - left, bottom - top
        if width <= box_width * 0.92 and height <= box_height * 0.92:
            return candidate
    return _font(min_size)


def _render_text(image: Image.Image, text: str, bbox: list[float]) -> None:
    x0, y0, x1, y1 = bbox
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    vertical = height > width * 1.55 and len(text) > 1
    draw = ImageDraw.Draw(image)
    font = _fit_font(text, width, height, vertical)
    if vertical:
        char_heights = [draw.textbbox((0, 0), char, font=font)[3] for char in text]
        total = sum(char_heights)
        y = y0 + max(0.0, (height - total) / 2)
        for char, char_height in zip(text, char_heights, strict=False):
            bounds = draw.textbbox((0, 0), char, font=font)
            char_width = bounds[2] - bounds[0]
            draw.text((x0 + max(0.0, (width - char_width) / 2), y), char,
                      font=font, fill=(0, 0, 0), stroke_width=0)
            y += char_height
        return
    bounds = draw.multiline_textbbox((0, 0), text, font=font, spacing=1)
    text_width, text_height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    draw.multiline_text(
        (x0 + max(0.0, (width - text_width) / 2), y0 + max(0.0, (height - text_height) / 2)),
        text, font=font, fill=(0, 0, 0), align="center", spacing=1,
    )


def _paint_translations(content: bytes, items: list[dict[str, Any]], targets: list[str]) -> bytes:
    """Remove OCR boxes with OpenCV inpainting and draw fitted translations."""
    try:
        _fitz, np, _pil, _rapid = _optional_imports()
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - optional runtime dependency
        raise OCRUnavailable("漫画翻译需要 OpenCV 图像处理组件。") from exc

    source = Image.open(io.BytesIO(content)).convert("RGB")
    array = cv2.cvtColor(np.asarray(source), cv2.COLOR_RGB2BGR)
    mask = np.zeros(array.shape[:2], dtype=np.uint8)
    height, width = array.shape[:2]
    boxes: list[list[float]] = []
    for item in items:
        raw = item.get("bbox") or [0, 0, 0, 0]
        x0, y0, x1, y1 = [float(value) for value in raw]
        pad = max(2, int(min(width, height) * 0.006))
        left = max(0, int(x0) - pad)
        top = max(0, int(y0) - pad)
        right = min(width - 1, int(x1) + pad)
        bottom = min(height - 1, int(y1) + pad)
        if right <= left or bottom <= top:
            boxes.append([x0, y0, x1, y1])
            continue
        cv2.rectangle(mask, (left, top), (right, bottom), 255, thickness=-1)
        boxes.append([left, top, right, bottom])

    if np.any(mask):
        repaired = cv2.inpaint(array, mask, 3, cv2.INPAINT_TELEA)
        image = Image.fromarray(cv2.cvtColor(repaired, cv2.COLOR_BGR2RGB))
    else:
        image = source
    for box, target in zip(boxes, targets, strict=False):
        value = str(target or "").strip()
        if value:
            _render_text(image, value, box)
    output = io.BytesIO()
    source_format = source.format or "PNG"
    image.save(output, format="PNG" if source_format.upper() not in {"JPEG", "JPG", "WEBP"} else source_format)
    return output.getvalue()


def translate_comic(request: ComicTranslateRequest, translator: Any, ocr: OfflineOCR,
                    emit: Emit, cancel: threading.Event) -> None:
    output_dir = Path(request.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest = _load_manifest(manifest_path)
    pages = manifest.setdefault("pages", {})
    results: list[dict[str, Any]] = []
    completed = 0
    failed = 0

    if request.quality == "quality" and not request.profile_id:
        request = request.model_copy(update={"profile_id": "quality"})
    elif request.quality == "speed" and not request.profile_id:
        request = request.model_copy(update={"profile_id": "balanced"})

    for index, raw_path in enumerate(request.image_paths):
        source = Path(raw_path).expanduser().resolve()
        page_key = str(source)
        emit("page_start", {"index": index, "total": len(request.image_paths),
                             "file_name": source.name})
        if cancel.is_set():
            break
        if not source.is_file():
            failed += 1
            item = {"index": index, "source_path": str(source), "status": "failed",
                    "error": "找不到原图"}
            results.append(item)
            pages[page_key] = item
            _save_manifest(manifest_path, manifest)
            emit("page_error", {**item, "completed": completed, "failed": failed,
                                  "total": len(request.image_paths)})
            continue

        key = _file_key(source, request)
        record = pages.get(page_key, {})
        output_name = f"{index + 1:04d}-{source.stem}-{request.target_lang}.png"
        output_path = output_dir / output_name
        if (not request.force and record.get("key") == key
                and record.get("status") == "done" and output_path.is_file()):
            completed += 1
            item = {**record, "index": index, "output_path": str(output_path), "cached": True}
            results.append(item)
            emit("page_done", {**item, "completed": completed, "failed": failed,
                                 "total": len(request.image_paths)})
            continue

        try:
            content = source.read_bytes()
            detected = ocr.image(content, source_name=source.name)
            items = [item for item in detected.get("items", []) if str(item.get("text", "")).strip()]
            if not items:
                output_path.write_bytes(content)
                item = {"index": index, "source_path": str(source), "output_path": str(output_path),
                        "status": "done", "key": key, "text_count": 0, "cached": False,
                        "no_text": True}
                pages[page_key] = item
                _save_manifest(manifest_path, manifest)
                completed += 1
                results.append(item)
                emit("page_done", {**item, "completed": completed, "failed": failed,
                                     "total": len(request.image_paths)})
                continue
            lines = [str(item["text"]) for item in items]
            request_for_page = ScreenshotTranslateRequest(
                lines=lines,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                profile_id=request.profile_id,
                device=request.device,
                glossary_id=request.glossary_id,
                style=request.style,
                use_tm=request.use_tm,
            )
            events: list[tuple[str, dict[str, Any]]] = []

            def collect(event: str, data: dict[str, Any] | None = None,
                        *, page_index: int = index, page_events=events) -> None:
                payload = data or {}
                page_events.append((event, payload))
                if event == "item_start":
                    emit("status", {"index": page_index, "total": len(request.image_paths),
                                     "message": f"正在翻译第 {page_index + 1} 页文字"})

            translator.run_lines(request_for_page, collect, cancel)
            error = next((data for event, data in reversed(events) if event == "error"), None)
            done = next((data for event, data in reversed(events) if event == "done"), None)
            if error:
                raise RuntimeError(error.get("message", "页面翻译失败"))
            if not done or done.get("cancelled"):
                if cancel.is_set():
                    break
                raise RuntimeError("页面翻译没有返回结果")
            targets = list(done.get("targets") or [])
            if len(targets) < len(items):
                targets.extend(lines[len(targets):])
            output_path.write_bytes(_paint_translations(content, items, targets))
            item = {"index": index, "source_path": str(source), "output_path": str(output_path),
                    "status": "done", "key": key, "text_count": len(items), "cached": False}
            pages[page_key] = item
            _save_manifest(manifest_path, manifest)
            completed += 1
            results.append(item)
            emit("page_done", {**item, "completed": completed, "failed": failed,
                                 "total": len(request.image_paths)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Comic page translation failed: %s", source)
            failed += 1
            item = {"index": index, "source_path": str(source), "status": "failed",
                    "error": str(exc), "key": key}
            pages[page_key] = item
            _save_manifest(manifest_path, manifest)
            results.append(item)
            emit("page_error", {**item, "completed": completed, "failed": failed,
                                  "total": len(request.image_paths)})

    cancelled = cancel.is_set()
    status = "cancelled" if cancelled else ("completed" if failed == 0 else "partial")
    manifest.update({"status": status, "completed": completed, "failed": failed,
                     "total": len(request.image_paths), "target_lang": request.target_lang,
                     "quality": request.quality})
    _save_manifest(manifest_path, manifest)
    emit("done", {"status": status, "completed": completed, "failed": failed,
                   "total": len(request.image_paths), "results": results,
                   "manifest_path": str(manifest_path), "cancelled": cancelled})
