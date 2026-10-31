from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..schemas import SpeechSessionRequest, SpeechSessionStartRequest
from .common import error_response

router = APIRouter(prefix="/api/speech", tags=["speech"])


@router.get("/status")
async def speech_status(request: Request):
    return request.app.state.speech.model_status()


@router.post("/model/download")
async def speech_model_download(request: Request):
    return request.app.state.speech.start_download()


@router.post("/session/start")
async def speech_session_start(body: SpeechSessionStartRequest, request: Request):
    try:
        return request.app.state.speech.start_session(body.mode)
    except ValueError as exc:
        return error_response(422, "INVALID_SPEECH_MODE", str(exc))
    except RuntimeError as exc:
        return error_response(409, "SPEECH_UNAVAILABLE", str(exc))


@router.post("/session/stop")
async def speech_session_stop(body: SpeechSessionRequest, request: Request):
    try:
        return request.app.state.speech.stop_session(body.session_id)
    except KeyError as exc:
        return error_response(404, "SPEECH_SESSION_NOT_FOUND", str(exc))


@router.get("/session/status")
async def speech_session_status(
    request: Request,
    session_id: str = Query(min_length=1, max_length=64),
    since: int = Query(default=0, ge=0),
):
    try:
        return request.app.state.speech.session_status(session_id, since)
    except KeyError as exc:
        return error_response(404, "SPEECH_SESSION_NOT_FOUND", str(exc))
