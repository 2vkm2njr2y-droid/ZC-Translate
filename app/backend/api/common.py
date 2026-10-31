from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

SSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
}


def sse(event: str, data: dict[str, Any] | None = None) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def job_stream_response(job: Any, request: Request) -> StreamingResponse:
    """Forward a JobQueue job's events as SSE, cancelling on disconnect."""

    async def event_stream():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(job.events.get(), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    if await request.is_disconnected():
                        job.cancel.set()
                        break
                    continue
                yield sse(item["event"], item["data"])
                if item["event"] in {"done", "error"}:
                    break
                if await request.is_disconnected():
                    job.cancel.set()
                    break
        finally:
            if job.state in {"queued", "running"}:
                job.cancel.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={**SSE_HEADERS, "X-Job-Id": job.id},
    )


def error_response(status_code: int, code: str, message: str,
                   detail: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail:
        body["error"]["detail"] = detail
    return JSONResponse(body, status_code=status_code)


def settings_for(request: Request) -> dict[str, Any]:
    from ..services.settings import load_settings
    return load_settings(request.app.state.db)
