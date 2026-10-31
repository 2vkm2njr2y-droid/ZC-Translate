from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..schemas import TranslateRequest
from ..services.jobs import QueueFull
from .common import error_response, job_stream_response

router = APIRouter(prefix="/api", tags=["translate"])


@router.post("/translate/stream")
async def translate_stream(body: TranslateRequest, request: Request):
    app = request.app
    loop = asyncio.get_running_loop()

    def run_job(emit, cancel):
        app.state.translator.run(body, emit, cancel)

    try:
        job = app.state.jobs.submit("translate", run_job, loop)
    except QueueFull as exc:
        return error_response(429, "QUEUE_FULL", str(exc))

    return job_stream_response(job, request)


@router.post("/translate")
async def translate_once(body: TranslateRequest, request: Request):
    app = request.app
    events: list[tuple[str, dict]] = []
    cancel = threading.Event()

    def emit(event: str, data: dict | None = None) -> None:
        events.append((event, data or {}))

    await asyncio.to_thread(app.state.translator.run, body, emit, cancel)

    for event, data in events:
        if event == "error":
            return JSONResponse(data, status_code=502)
        if event == "done":
            return data
    return error_response(500, "NO_RESULT", "翻译未返回结果")


@router.post("/translate/cancel/{job_id}")
async def cancel_translation(job_id: str, request: Request):
    cancelled = request.app.state.jobs.cancel(job_id)
    return {"cancelled": cancelled, "job_id": job_id}


@router.get("/translate/jobs")
async def job_status(request: Request):
    return request.app.state.jobs.counts()
