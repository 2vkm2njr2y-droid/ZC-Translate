from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from ..schemas import ComicTranslateRequest
from ..services.comic import translate_comic
from ..services.jobs import QueueFull
from ..services.ocr import OfflineOCR
from .common import error_response, job_stream_response

router = APIRouter(prefix="/api/comic", tags=["comic"])
_ocr = OfflineOCR()


@router.post("/translate/stream")
async def translate_comic_stream(body: ComicTranslateRequest, request: Request):
    app = request.app
    loop = asyncio.get_running_loop()

    def run_job(emit, cancel):
        translate_comic(body, app.state.translator, _ocr, emit, cancel)

    try:
        job = app.state.jobs.submit("comic", run_job, loop)
    except QueueFull as exc:
        return error_response(429, "QUEUE_FULL", str(exc))

    return job_stream_response(job, request)
