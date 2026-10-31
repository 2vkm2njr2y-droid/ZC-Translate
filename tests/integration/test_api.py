from __future__ import annotations

import base64
import io

from docx import Document
from fastapi.testclient import TestClient

from app.backend.api import comic as comic_api
from app.backend.api import ocr as ocr_api
from app.backend.api import screenshot as screenshot_api
from app.backend.main import create_app
from app.backend.services.screenshot import CaptureCancelled, CaptureUnavailable


def make_client(tmp_path):
    app = create_app(
        token="test-token",
        data_dir=str(tmp_path / "data"),
        models_dir=str(tmp_path / "models"),
    )
    return TestClient(app), {"X-ZC-Token": "test-token"}


class FakeDocxTranslator:
    def run(self, request, emit, cancel):
        emit("done", {"text": f"译:{request.text}"})


class CancelAfterFirstDocxTranslator(FakeDocxTranslator):
    def run(self, request, emit, cancel):
        super().run(request, emit, cancel)
        cancel.set()


def _docx_bytes(*paragraphs: str) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_health_and_auth(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/settings").status_code == 401
        assert client.get("/api/settings", headers=headers).status_code == 200


def test_index_requires_token(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        assert client.get("/").status_code == 403
        response = client.get("/", params={"token": "test-token"})
        assert response.status_code == 200
        assert "ZC 离线翻译" in response.text
        assert "__ZC_TOKEN__" not in response.text


def test_models_and_settings(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        models = client.get("/api/models", headers=headers).json()
        assert {item["profile_id"] for item in models["models"]} == {"balanced", "quality"}
        assert all(not item["installed"] for item in models["models"])
        updated = client.put("/api/settings", headers=headers,
                             json={"target_lang": "ja", "theme": "dark"}).json()
        assert updated["target_lang"] == "ja"
        assert updated["theme"] == "dark"
        assert updated["selection_translate"] is False
        updated = client.put(
            "/api/settings", headers=headers, json={"selection_translate": True}
        ).json()
        assert updated["selection_translate"] is True
        assert client.get("/api/settings", headers=headers).json()["selection_translate"] is True


def test_speech_status_and_missing_model_error(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        status = client.get("/api/speech/status", headers=headers)
        assert status.status_code == 200
        assert status.json()["installed"] is False
        response = client.post(
            "/api/speech/session/start",
            headers=headers,
            json={"mode": "conversation"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SPEECH_UNAVAILABLE"


def test_overlay_page_requires_token_and_injects_it(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        assert client.get("/overlay").status_code == 403
        response = client.get("/overlay", params={"token": "test-token"})
        assert response.status_code == 200
        assert "__ZC_TOKEN__" not in response.text
        assert 'name="zc-token" content="test-token"' in response.text
        assert "/js/overlay.js" in response.text
        assert response.headers.get("cache-control") == "no-store"


def test_glossary_crud_and_export(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        created = client.post("/api/glossaries", headers=headers, json={
            "name": "技术", "src_lang": "en", "tgt_lang": "zh", "bidirectional": True,
        })
        assert created.status_code == 201
        gid = created.json()["id"]
        term = client.post(f"/api/glossaries/{gid}/terms", headers=headers, json={
            "source": "cache", "target": "缓存", "note": "n",
        })
        assert term.status_code == 200
        terms = client.get(f"/api/glossaries/{gid}/terms", headers=headers).json()["items"]
        assert terms[0]["target"] == "缓存"
        exported = client.get(f"/api/glossaries/{gid}/export", headers=headers)
        assert exported.status_code == 200
        assert "cache" in exported.text
        assert client.delete(f"/api/glossaries/{gid}", headers=headers).status_code == 200


def test_history_empty(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        data = client.get("/api/history", headers=headers).json()
        assert data == {"total": 0, "items": []}


def test_history_delete_and_clear(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        db = client.app.state.db
        ids = [
            db.add_history(
                kind="text",
                src_lang="en",
                detected_lang="en",
                tgt_lang="zh",
                profile="balanced",
                device="CPU",
                source_text=text,
                result_text=f"译:{text}",
                status="completed",
                duration_ms=5,
            )
            for text in ("one", "two")
        ]
        listing = client.get("/api/history", headers=headers).json()
        assert listing["total"] == 2

        assert client.delete(f"/api/history/{ids[0]}", headers=headers).status_code == 200
        assert client.get(f"/api/history/{ids[0]}", headers=headers).status_code == 404
        assert client.get("/api/history", headers=headers).json()["total"] == 1

        assert client.delete("/api/history", headers=headers).status_code == 200
        assert client.get("/api/history", headers=headers).json() == {"total": 0, "items": []}


def test_system_info_and_doctor(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        info = client.get("/api/system/info", headers=headers)
        assert info.status_code == 200
        assert "openvino" in info.json()
        doctor = client.post("/api/system/doctor", headers=headers)
        assert doctor.status_code == 200
        assert "checks" in doctor.json()


class FakeLineTranslator:
    def run_lines(self, body, emit, cancel):
        emit("status", {"phase": "loading", "message": "fake"})
        emit("meta", {"src_lang": "en", "tgt_lang": body.target_lang, "count": len(body.lines)})
        for index, line in enumerate(body.lines):
            emit("item_start", {"index": index})
            emit("item_delta", {"index": index, "text": "译"})
            emit("item_done", {"index": index, "text": f"译{line}", "tm_hit": False,
                               "warnings": [], "glossary_hits": 0, "gen_tokens": 1,
                               "tok_s": 10.0, "ttft_ms": 1.0})
        emit("done", {"status": "completed", "targets": [f"译{line}" for line in body.lines],
                      "text": "\n".join(f"译{line}" for line in body.lines),
                      "cancelled": False, "elapsed_ms": 5, "gen_tokens": 2,
                      "tok_s": 10.0, "device": "CPU", "model": "Fake", "warnings": []})


def test_screenshot_translate_stream(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        client.app.state.translator = FakeLineTranslator()
        response = client.post(
            "/api/screenshot/translate/stream",
            headers=headers,
            json={"lines": ["hello", "world"], "source_lang": "en", "target_lang": "zh"},
        )
        assert response.status_code == 200
        assert response.headers.get("X-Job-Id")
        text = response.text
        assert "event: meta" in text
        assert "event: item_done" in text
        assert "event: done" in text
        assert "译hello" in text


def test_screenshot_empty_lines_are_rejected(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        response = client.post(
            "/api/screenshot/translate/stream",
            headers=headers,
            json={"lines": [""], "source_lang": "en", "target_lang": "zh"},
        )
        assert response.status_code == 422


def test_screenshot_capture_errors(tmp_path, monkeypatch):
    client, headers = make_client(tmp_path)
    with client:
        monkeypatch.setattr(
            screenshot_api, "capture_native_region",
            lambda: (_ for _ in ()).throw(CaptureCancelled("cancelled")),
        )
        response = client.post("/api/screenshot/capture", headers=headers)
        assert response.status_code == 408
        assert response.json()["error"]["code"] == "SCREENSHOT_CANCELLED"

        monkeypatch.setattr(
            screenshot_api, "capture_native_region",
            lambda: (_ for _ in ()).throw(CaptureUnavailable("missing")),
        )
        response = client.post("/api/screenshot/capture", headers=headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SCREENSHOT_UNAVAILABLE"


def test_ocr_image_returns_detected_language(tmp_path, monkeypatch):
    client, headers = make_client(tmp_path)
    with client:
        monkeypatch.setattr(
            ocr_api._ocr,
            "image",
            lambda content, source_name="image": {
                "file_name": source_name, "width": 10, "height": 10,
                "text": "こんにちは", "items": [],
            },
        )
        response = client.post(
            "/api/ocr/image",
            headers=headers,
            json={"file_name": "shot.png",
                  "content_base64": base64.b64encode(b"not-an-image").decode("ascii")},
        )
        assert response.status_code == 200
        assert response.json()["detected_lang"] == "ja"


def test_document_translate_stream_returns_progress_and_file(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        client.app.state.translator = FakeDocxTranslator()
        source = tmp_path / "sample.docx"
        source.write_bytes(_docx_bytes("hello"))
        response = client.post(
            "/api/document/translate/stream",
            headers=headers,
            json={
                "file_name": "sample.docx",
                "source_path": str(source),
                "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
                "source_lang": "en",
                "target_lang": "zh",
            },
        )

        assert response.status_code == 200
        assert "event: meta" in response.text
        assert "event: progress" in response.text
        assert "event: done" in response.text
        target = source.with_name("sample_翻译.docx")
        assert target.is_file()
        assert [p.text for p in Document(target).paragraphs] == ["译:hello"]


def test_document_translate_stream_cancel_stops_without_file(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        client.app.state.translator = CancelAfterFirstDocxTranslator()
        source = tmp_path / "cancel.docx"
        source.write_bytes(_docx_bytes("hello", "world"))
        response = client.post(
            "/api/document/translate/stream",
            headers=headers,
            json={
                "file_name": "cancel.docx",
                "source_path": str(source),
                "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
                "source_lang": "en",
                "target_lang": "zh",
            },
        )

        assert response.status_code == 200
        assert '"cancelled": true' in response.text
        assert not source.with_name("cancel_翻译.docx").exists()


def test_document_translate_stream_browser_fallback(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        client.app.state.translator = FakeDocxTranslator()
        response = client.post(
            "/api/document/translate/stream",
            headers=headers,
            json={
                "file_name": "sample.docx",
                "content_base64": base64.b64encode(_docx_bytes("hello")).decode("ascii"),
                "source_lang": "en",
                "target_lang": "zh",
            },
        )

        assert response.status_code == 200
        assert '"content_base64": "' in response.text
        assert not (tmp_path / "sample_翻译.docx").exists()


def test_document_translate_legacy_endpoint_still_works(tmp_path):
    client, headers = make_client(tmp_path)
    with client:
        client.app.state.translator = FakeDocxTranslator()
        source = tmp_path / "legacy.docx"
        source.write_bytes(_docx_bytes("hello"))
        response = client.post(
            "/api/document/translate",
            headers=headers,
            json={
                "file_name": "legacy.docx",
                "source_path": str(source),
                "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
                "source_lang": "en",
                "target_lang": "zh",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["saved_path"] == str(source.with_name("legacy_翻译.docx"))
        assert data["segments"] == 1


def test_comic_translate_stream_still_queues_job(tmp_path, monkeypatch):
    client, headers = make_client(tmp_path)
    with client:
        image = tmp_path / "page.png"
        image.write_bytes(b"x")
        output_dir = tmp_path / "out"
        output_dir.mkdir()

        def fake_translate_comic(body, translator, ocr, emit, cancel):
            emit("page_start", {"index": 0, "total": 1, "file_name": "page.png"})
            emit("page_done", {"index": 0, "status": "done", "output_path": "out.png"})
            emit("done", {"status": "completed", "completed": 1, "failed": 0, "total": 1})

        monkeypatch.setattr(comic_api, "translate_comic", fake_translate_comic)
        response = client.post(
            "/api/comic/translate/stream",
            headers=headers,
            json={
                "image_paths": [str(image)],
                "output_dir": str(output_dir),
                "source_lang": "en",
                "target_lang": "zh",
            },
        )

        assert response.status_code == 200
        assert "event: page_start" in response.text
        assert "event: page_done" in response.text
        assert "event: done" in response.text
