"""FastAPI application factory for the local translator backend."""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import comic, glossaries, history, models, ocr, screenshot, speech, system, translate
from .config import (
    APP_NAME,
    APP_VERSION,
    ensure_dirs,
    resolve_data_dir,
    resolve_frontend_dir,
    resolve_models_dir,
)
from .engine.registry import EngineManager
from .pipeline.translator import TranslationService
from .services.jobs import JobQueue
from .services.settings import load_settings
from .services.speech import SpeechService
from .storage.db import Database

logger = logging.getLogger(__name__)


def create_app(token: str | None = None, *, data_dir: str | None = None,
               models_dir: str | None = None, dev: bool = False) -> FastAPI:
    if data_dir:
        os.environ["ZC_DATA_DIR"] = str(data_dir)
    if models_dir:
        os.environ["ZC_MODELS_DIR"] = str(models_dir)
    ensure_dirs()

    database = Database(resolve_data_dir() / "app.db")
    engine = EngineManager(resolve_models_dir())
    jobs = JobQueue()
    jobs.start()
    translator = TranslationService(engine, database)
    speech_service = SpeechService(resolve_models_dir())
    token = token or secrets.token_urlsafe(24)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        current = load_settings(database)
        if current.get("preload_model") and engine.packs:
            engine.preload(str(current.get("profile_id", "balanced")), "auto")
        try:
            yield
        finally:
            jobs.shutdown()
            speech_service.shutdown()
            engine.unload()
            database.close()

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.token = token
    app.state.db = database
    app.state.engine = engine
    app.state.jobs = jobs
    app.state.translator = translator
    app.state.speech = speech_service

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health":
            provided = request.headers.get("x-zc-token", "")
            if provided != app.state.token:
                return JSONResponse(
                    {"error": {"code": "UNAUTHORIZED", "message": "本地会话令牌无效，请从启动器重新打开。"}},
                    status_code=401,
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        return response

    app.include_router(translate.router)
    app.include_router(comic.router)
    app.include_router(ocr.router)
    app.include_router(screenshot.router)
    app.include_router(speech.router)
    app.include_router(models.router)
    app.include_router(glossaries.router)
    app.include_router(history.router)
    app.include_router(system.router)

    frontend = resolve_frontend_dir()
    if (frontend / "assets").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
    if (frontend / "js").exists():
        app.mount("/js", StaticFiles(directory=frontend / "js"), name="js")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": APP_VERSION}

    @app.get("/favicon.ico")
    async def favicon():
        # A 204 response must not carry a body; returning a JSON body here
        # makes h11 report "Too much data for declared Content-Length".
        return Response(status_code=204)

    def render_page(file_name: str, request: Request) -> HTMLResponse:
        provided = request.query_params.get("token") or request.headers.get("x-zc-token", "")
        if provided != app.state.token:
            return HTMLResponse(
                "<!doctype html><meta charset='utf-8'>"
                "<body style='font-family:system-ui;padding:40px;background:#0b1220;color:#e5e7eb'>"
                "<h2>请从桌面启动器打开</h2>"
                "<p>为安全起见，本地服务只接受启动器生成的一次性令牌。</p></body>",
                status_code=403,
            )
        page_path = frontend / file_name
        if not page_path.exists():
            return HTMLResponse("<h2>前端文件缺失</h2>", status_code=500)
        html = page_path.read_text(encoding="utf-8")
        html = html.replace("__ZC_TOKEN__", app.state.token).replace(
            "__APP_VERSION__", APP_VERSION
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/")
    async def index(request: Request):
        return render_page("index.html", request)

    @app.get("/overlay")
    async def overlay(request: Request):
        return render_page("overlay.html", request)

    return app
