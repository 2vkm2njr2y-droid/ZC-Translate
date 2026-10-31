from __future__ import annotations

import threading
from types import SimpleNamespace

from app.backend.engine.base import GenerationResult
from app.backend.pipeline.translator import TranslationService
from app.backend.schemas import TranslateRequest
from app.backend.storage.db import Database


class FakeManager:
    def __init__(self, output: str = "译文") -> None:
        self.output = output
        self.pack = SimpleNamespace(name="Fake Model")
        self.calls = 0

    def ensure_loaded(self, profile_id, device="auto", on_status=None):
        if on_status:
            on_status("fake loaded")
        return SimpleNamespace(device="CPU", warning="")

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 3)

    def generate(self, messages, options, on_token, cancel_event):
        self.calls += 1
        on_token(self.output[:1])
        on_token(self.output[1:])
        return GenerationResult(
            text=self.output, device="CPU", model_id="fake", gen_tokens=2,
            ttft_ms=5.0, total_ms=15.0, tok_s=200.0,
        )


def run(service, text="hello", src="en", tgt="zh"):
    events = []
    cancel = threading.Event()
    request = TranslateRequest(text=text, source_lang=src, target_lang=tgt)
    service.run(request, lambda event, data=None: events.append((event, data or {})), cancel)
    return events


def test_streaming_events_and_history(db: Database):
    service = TranslationService(FakeManager(), db)
    events = run(service, "hello", "en", "zh")
    names = [event for event, _ in events]
    assert names[0] == "status"
    assert "meta" in names
    assert names.count("delta") == 2
    assert names[-1] == "done"
    done = events[-1][1]
    assert done["status"] == "completed"
    assert done["text"] == "译文"
    assert db.list_history()["total"] == 1


def test_translation_memory_hit(db: Database):
    service = TranslationService(FakeManager(), db)
    run(service, "hello", "en", "zh")
    events = run(service, "hello", "en", "zh")
    block_done = [data for event, data in events if event == "block_done"][0]
    assert block_done["tm_hit"] is True
    assert block_done["text"] == "译文"


def test_cancellation(db: Database):
    service = TranslationService(FakeManager(), db)
    events = []
    cancel = threading.Event()
    cancel.set()
    request = TranslateRequest(text="hello", source_lang="en", target_lang="zh")
    service.run(request, lambda event, data=None: events.append((event, data or {})), cancel)
    done = [data for event, data in events if event == "done"][0]
    assert done["status"] == "cancelled"
    assert db.list_history()["items"][0]["status"] == "cancelled"


def test_same_language_is_rejected(db: Database):
    service = TranslationService(FakeManager(), db)
    events = run(service, "hello", "en", "en")
    assert events[-1][0] == "error"
    assert "相同" in events[-1][1]["message"]


def test_auto_detection(db: Database):
    service = TranslationService(FakeManager(), db)
    events = run(service, "こんにちは。", "auto", "zh")
    meta = [data for event, data in events if event == "meta"][0]
    assert meta["src_lang"] == "ja"
