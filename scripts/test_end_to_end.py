from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.engine.registry import EngineManager, scan_models  # noqa: E402
from app.backend.pipeline.translator import TranslationService  # noqa: E402
from app.backend.schemas import TranslateRequest  # noqa: E402
from app.backend.storage.db import Database  # noqa: E402

print("packs:", {key: pack.as_dict() for key, pack in scan_models().items()})
engine = EngineManager()
print("devices:", engine.resolver.describe())
resolved = engine.ensure_loaded("balanced", "auto")
print("loaded:", resolved.device, resolved.variant, "load_ms", engine.engine.load_ms)

with tempfile.TemporaryDirectory() as tmp:
    db = Database(Path(tmp) / "test.db")
    service = TranslationService(engine, db)
    cases = [
        ("zh", "ja", "今天天气真好。我们下午去公园散步吧。"),
        ("ja", "zh", "会議の資料は昨日のうちに全員に送っておきました。"),
        ("en", "zh", "The update fixes a crash when the cache directory is missing."),
    ]
    results = []
    for src, tgt, text in cases:
        events = []
        cancel = threading.Event()

        def emit(event, data=None, events=events):
            events.append((event, data or {}))

        req = TranslateRequest(text=text, source_lang=src, target_lang=tgt, device="auto")
        service.run(req, emit, cancel)
        done = [data for event, data in events if event == "done"]
        errors = [data for event, data in events if event == "error"]
        results.append({
            "src": src, "tgt": tgt, "source": text,
            "error": errors[-1] if errors else None,
            "done": done[-1] if done else None,
            "block_warnings": [data.get("warnings") for event, data in events
                               if event == "block_done"],
        })
        print(f"CASE {src}->{tgt} error={bool(errors)} done={bool(done)}")
    Path("data/e2e.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    db.close()
engine.unload()
