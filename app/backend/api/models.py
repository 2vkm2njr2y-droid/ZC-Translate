from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import MODEL_PROFILES
from ..engine.base import EngineError
from ..services.settings import load_settings, update_settings
from .common import error_response

router = APIRouter(prefix="/api/models", tags=["models"])


def _model_view(profile: dict[str, Any], pack, engine) -> dict[str, Any]:
    view: dict[str, Any] = {
        "profile_id": profile["id"],
        "name": profile["name"],
        "description": profile["description"],
        "params": profile["params"],
        "license": profile["license"],
        "devices": profile["devices"],
        "optional": profile["optional"],
        "repo": profile["repo"],
        "installed": bool(pack and pack.ready),
        "path": str(pack.path) if pack else "",
        "variants": {},
        "size_bytes": 0,
        "error": pack.error if pack else "未安装",
    }
    if pack:
        view["variants"] = {key: str(path) for key, path in pack.variants.items()}
        view["size_bytes"] = pack.size_bytes()
        view["name"] = pack.name or view["name"]
        view["params"] = pack.params or view["params"]
        view["license"] = pack.license or view["license"]
    view["loaded"] = bool(
        engine.pack and pack and engine.pack.id == pack.id and engine.state == "ready"
    )
    return view


@router.get("")
async def list_models(request: Request):
    app = request.app
    engine = app.state.engine
    settings = load_settings(app.state.db)
    models = [_model_view(profile, engine.packs.get(str(profile["model_id"])), engine)
              for profile in MODEL_PROFILES.values()]
    return {
        "models": models,
        "active_profile": settings.get("profile_id", "balanced"),
        "engine": engine.status(),
        "models_dir": str(engine.models_dir),
    }


@router.post("/scan")
async def scan_models(request: Request):
    engine = request.app.state.engine
    engine.scan()
    return {"models": [pack.as_dict() for pack in engine.packs.values()],
            "models_dir": str(engine.models_dir)}


@router.post("/{profile_id}/activate")
async def activate_model(profile_id: str, request: Request):
    if profile_id not in MODEL_PROFILES:
        return error_response(404, "UNKNOWN_PROFILE", f"未知模型档位：{profile_id}")
    settings = update_settings(request.app.state.db, {"profile_id": profile_id})
    return {"ok": True, "active_profile": settings["profile_id"]}


@router.post("/{profile_id}/load")
async def load_model(profile_id: str, request: Request, device: str = "auto"):
    if profile_id not in MODEL_PROFILES:
        return error_response(404, "UNKNOWN_PROFILE", f"未知模型档位：{profile_id}")
    import asyncio

    app = request.app
    try:
        resolved = await asyncio.to_thread(app.state.engine.ensure_loaded, profile_id, device)
    except EngineError as exc:
        return error_response(503, "MODEL_LOAD_FAILED", str(exc))
    return {"ok": True, "device": resolved.device, "warning": resolved.warning,
            "engine": app.state.engine.status()}


@router.post("/unload")
async def unload_model(request: Request):
    request.app.state.engine.unload()
    return {"ok": True, "engine": request.app.state.engine.status()}


@router.post("/{profile_id}/open-folder")
async def open_folder(profile_id: str, request: Request):
    if profile_id not in MODEL_PROFILES:
        return error_response(404, "UNKNOWN_PROFILE", "未知模型档位")
    profile = MODEL_PROFILES[profile_id]
    pack = request.app.state.engine.packs.get(str(profile["model_id"]))
    target = pack.path if pack else request.app.state.engine.models_dir
    try:
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": {"code": "OPEN_FAILED", "message": str(exc)}},
                            status_code=500)
    return {"ok": True, "path": str(target)}
