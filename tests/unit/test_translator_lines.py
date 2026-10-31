from __future__ import annotations

import threading
from types import SimpleNamespace

from app.backend.engine.base import GenerationResult
from app.backend.pipeline.translator import TranslationService
from app.backend.schemas import ScreenshotTranslateRequest
from app.backend.storage.db import Database


class FakeManager:
    def __init__(self, output: str = "译文") -> None:
        self.output = output
        self.pack = SimpleNamespace(name="Fake Model")

    def ensure_loaded(self, profile_id, device="auto", on_status=None):
        if on_status:
            on_status("fake loaded")
        return SimpleNamespace(device="CPU", warning="")

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 3)

    def generate(self, messages, options, on_token, cancel_event):
        on_token(self.output[:1])
        on_token(self.output[1:])
        return GenerationResult(
            text=self.output, device="CPU", model_id="fake", gen_tokens=2,
            ttft_ms=5.0, total_ms=15.0, tok_s=200.0,
        )


def run_lines(service, lines, src="en", tgt="zh"):
    events = []
    cancel = threading.Event()
    request = ScreenshotTranslateRequest(lines=lines, source_lang=src, target_lang=tgt)
    service.run_lines(request, lambda event, data=None: events.append((event, data or {})), cancel)
    return events


def test_line_events_and_single_history(db: Database):
    service = TranslationService(FakeManager(), db)
    events = run_lines(service, ["hello", "world"])
    names = [event for event, _ in events]
    assert names[0] == "status"
    assert names.count("item_start") == 2
    assert names.count("item_done") == 2
    assert names[-1] == "done"
    done = events[-1][1]
    assert done["status"] == "completed"
    assert done["targets"] == ["译文", "译文"]
    history = db.list_history()
    assert history["total"] == 1
    assert history["items"][0]["kind"] == "screenshot"


def test_line_memory_hit(db: Database):
    service = TranslationService(FakeManager(), db)
    run_lines(service, ["hello"])
    events = run_lines(service, ["hello"])
    item_done = [data for event, data in events if event == "item_done"][0]
    assert item_done["tm_hit"] is True
    assert item_done["text"] == "译文"


def test_line_same_language_is_rejected(db: Database):
    service = TranslationService(FakeManager(), db)
    events = run_lines(service, ["hello"], "en", "en")
    error = [data for event, data in events if event == "error"][0]
    assert error["code"] == "SAME_LANGUAGE"
    assert db.list_history()["total"] == 0


def test_line_unknown_language_is_rejected(db: Database):
    service = TranslationService(FakeManager(), db)
    events = run_lines(service, ["123"], "auto", "zh")
    error = [data for event, data in events if event == "error"][0]
    assert error["code"] == "LANG_UNKNOWN"


def test_line_cancellation(db: Database):
    service = TranslationService(FakeManager(), db)
    events = []
    cancel = threading.Event()
    cancel.set()
    request = ScreenshotTranslateRequest(lines=["hello"], source_lang="en", target_lang="zh")
    service.run_lines(request, lambda event, data=None: events.append((event, data or {})), cancel)
    done = [data for event, data in events if event == "done"][0]
    assert done["status"] == "cancelled"


def test_empty_output_falls_back_to_source(db: Database):
    service = TranslationService(FakeManager(output=""), db)
    events = run_lines(service, ["hello"])
    item_done = [data for event, data in events if event == "item_done"][0]
    assert item_done["text"] == "hello"
    assert any("保留原文" in warning for warning in item_done["warnings"])


def test_short_line_length_warning_is_suppressed(db: Database):
    service = TranslationService(FakeManager(output="译文"), db)
    events = run_lines(service, ["A long English sentence for testing"])
    item_done = [data for event, data in events if event == "item_done"][0]
    assert not any("译文明显偏短" in warning for warning in item_done["warnings"])
