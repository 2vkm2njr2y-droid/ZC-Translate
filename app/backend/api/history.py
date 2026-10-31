from __future__ import annotations

import json

from fastapi import APIRouter, Request

from .common import error_response

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def list_history(request: Request, query: str = "", limit: int = 20, offset: int = 0):
    return request.app.state.db.list_history(query=query, limit=limit, offset=offset)


@router.get("/{history_id}")
async def get_history(history_id: str, request: Request):
    item = request.app.state.db.get_history(history_id)
    if not item:
        return error_response(404, "NOT_FOUND", "历史记录不存在")
    try:
        item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
    except json.JSONDecodeError:
        item["warnings"] = []
    return item


@router.delete("/{history_id}")
async def delete_history(history_id: str, request: Request):
    request.app.state.db.delete_history(history_id)
    return {"ok": True}


@router.delete("")
async def clear_history(request: Request):
    request.app.state.db.clear_history()
    return {"ok": True}
