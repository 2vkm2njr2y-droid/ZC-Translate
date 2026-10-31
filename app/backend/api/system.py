from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from ..schemas import SettingsUpdate
from ..services.diagnostics import collect_system_info, run_doctor
from ..services.settings import load_settings, update_settings
from .common import error_response

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/system/info")
async def system_info(request: Request):
    app = request.app
    return collect_system_info(app.state.db, app.state.engine, app.state.jobs)


@router.post("/system/doctor")
async def doctor(request: Request):
    app = request.app
    settings = load_settings(app.state.db)
    return run_doctor(app.state.db, app.state.engine, settings)


@router.get("/settings")
async def get_settings(request: Request):
    return load_settings(request.app.state.db)


@router.put("/settings")
async def put_settings(body: SettingsUpdate, request: Request):
    updates = body.model_dump(exclude_none=True)
    return update_settings(request.app.state.db, updates)


@router.get("/system/devices")
async def devices(request: Request):
    engine = request.app.state.engine
    return {"devices": engine.resolver.describe(), "engine": engine.status()}


@router.post("/system/preload")
async def preload(request: Request):
    app = request.app
    settings = load_settings(app.state.db)
    profile = str(settings.get("profile_id", "balanced"))
    try:
        resolved = await asyncio.to_thread(app.state.engine.ensure_loaded, profile, "auto")
    except Exception as exc:  # noqa: BLE001
        return error_response(503, "MODEL_LOAD_FAILED", str(exc))
    return {"ok": True, "device": resolved.device, "engine": app.state.engine.status()}


@router.get("/system/tm")
async def tm_stats(request: Request):
    return request.app.state.db.tm_stats()


@router.delete("/system/tm")
async def clear_tm(request: Request):
    request.app.state.db.clear_tm()
    return {"ok": True}
