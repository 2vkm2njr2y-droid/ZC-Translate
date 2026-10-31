from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from ..schemas import ScreenshotTranslateRequest
from ..services.jobs import QueueFull
from ..services.screenshot import (
    CaptureBusy,
    CaptureCancelled,
    CaptureError,
    CaptureTimeout,
    CaptureUnavailable,
    capture_native_region,
)
from .common import error_response, job_stream_response

router = APIRouter(prefix="/api", tags=["screenshot"])


@router.post("/screenshot/capture")
async def capture_screenshot():
    try:
        payload = await asyncio.to_thread(capture_native_region)
        return payload
    except CaptureBusy as exc:
        return error_response(409, "SCREENSHOT_BUSY", str(exc))
    except CaptureCancelled as exc:
        return error_response(408, "SCREENSHOT_CANCELLED", str(exc))
    except CaptureTimeout as exc:
        return error_response(504, "SCREENSHOT_TIMEOUT", str(exc))
    except CaptureUnavailable as exc:
        return error_response(503, "SCREENSHOT_UNAVAILABLE", str(exc))
    except CaptureError as exc:
        return error_response(500, "SCREENSHOT_FAILED", f"截图失败：{exc}")
    except Exception as exc:  # noqa: BLE001
        return error_response(500, "SCREENSHOT_FAILED", f"截图失败：{exc}")


@router.post("/screenshot/translate/stream")
async def screenshot_translate_stream(body: ScreenshotTranslateRequest, request: Request):
    app = request.app
    loop = asyncio.get_running_loop()

    def run_job(emit, cancel):
        app.state.translator.run_lines(body, emit, cancel)

    try:
        job = app.state.jobs.submit("screenshot", run_job, loop)
    except QueueFull as exc:
        return error_response(429, "QUEUE_FULL", str(exc))

    return job_stream_response(job, request)
