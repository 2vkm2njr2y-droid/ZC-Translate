from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..schemas import GlossaryCreate, GlossaryUpdate, ImportTermsRequest, TermCreate, TermUpdate
from ..services.settings import load_settings
from .common import error_response

router = APIRouter(prefix="/api/glossaries", tags=["glossaries"])


def _glossary_or_404(request: Request, glossary_id: str):
    return request.app.state.db.get_glossary(glossary_id)


@router.get("")
async def list_glossaries(request: Request):
    return {"items": request.app.state.db.list_glossaries()}


@router.post("", status_code=201)
async def create_glossary(body: GlossaryCreate, request: Request):
    glossary = request.app.state.db.create_glossary(
        body.name, body.src_lang, body.tgt_lang, body.bidirectional
    )
    return glossary


@router.put("/{glossary_id}")
async def update_glossary(glossary_id: str, body: GlossaryUpdate, request: Request):
    glossary = request.app.state.db.update_glossary(
        glossary_id, name=body.name, bidirectional=body.bidirectional
    )
    if not glossary:
        return error_response(404, "NOT_FOUND", "术语库不存在")
    return glossary


@router.delete("/{glossary_id}")
async def delete_glossary(glossary_id: str, request: Request):
    if not _glossary_or_404(request, glossary_id):
        return error_response(404, "NOT_FOUND", "术语库不存在")
    request.app.state.db.delete_glossary(glossary_id)
    settings = load_settings(request.app.state.db)
    if settings.get("glossary_id") == glossary_id:
        from ..services.settings import update_settings
        update_settings(request.app.state.db, {"glossary_id": ""})
    return {"ok": True}


@router.get("/{glossary_id}/terms")
async def list_terms(glossary_id: str, request: Request, query: str = ""):
    if not _glossary_or_404(request, glossary_id):
        return error_response(404, "NOT_FOUND", "术语库不存在")
    return {"items": request.app.state.db.list_terms(glossary_id, query)}


@router.post("/{glossary_id}/terms")
async def upsert_term(glossary_id: str, body: TermCreate, request: Request):
    if not _glossary_or_404(request, glossary_id):
        return error_response(404, "NOT_FOUND", "术语库不存在")
    term = request.app.state.db.upsert_term(
        glossary_id, body.source, body.target, body.case_sensitive, body.note
    )
    return term


@router.put("/{glossary_id}/terms/{term_id}")
async def update_term(glossary_id: str, term_id: int, body: TermUpdate,
                      request: Request):
    term = request.app.state.db.update_term(
        glossary_id, term_id, source=body.source, target=body.target,
        case_sensitive=body.case_sensitive, note=body.note,
    )
    if not term:
        return error_response(404, "NOT_FOUND", "术语不存在")
    return term


@router.delete("/{glossary_id}/terms/{term_id}")
async def delete_term(glossary_id: str, term_id: int, request: Request):
    request.app.state.db.delete_term(glossary_id, term_id)
    return {"ok": True}


@router.post("/{glossary_id}/import")
async def import_terms(glossary_id: str, body: ImportTermsRequest, request: Request):
    if not _glossary_or_404(request, glossary_id):
        return error_response(404, "NOT_FOUND", "术语库不存在")
    result = request.app.state.db.import_terms(glossary_id, body.csv_text, body.replace)
    return result


@router.get("/{glossary_id}/export")
async def export_terms(glossary_id: str, request: Request):
    if not _glossary_or_404(request, glossary_id):
        return error_response(404, "NOT_FOUND", "术语库不存在")
    csv_text = request.app.state.db.export_terms_csv(glossary_id)
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="glossary-{glossary_id}.csv"'},
    )
