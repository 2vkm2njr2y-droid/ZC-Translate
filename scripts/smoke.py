from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.config import ensure_dirs  # noqa: E402
from app.backend.engine.registry import EngineManager  # noqa: E402
from app.backend.pipeline.translator import TranslationService  # noqa: E402
from app.backend.schemas import TranslateRequest  # noqa: E402
from app.backend.storage.db import Database  # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="ZC 翻译引擎冒烟测试")
    parser.add_argument("--profile", default="balanced", choices=["balanced", "quality"])
    parser.add_argument("--device", default="auto", choices=["auto", "NPU", "GPU", "CPU"])
    parser.add_argument("--src", default="zh", choices=["auto", "zh", "ja", "en"])
    parser.add_argument("--tgt", default="ja", choices=["zh", "ja", "en"])
    parser.add_argument("--text", default="今天天气真好。我们下午去公园散步吧。")
    args = parser.parse_args()

    ensure_dirs()
    engine = EngineManager()
    started = time.perf_counter()
    try:
        resolved = engine.ensure_loaded(args.profile, args.device)
    except Exception as exc:  # noqa: BLE001
        print(f"加载失败: {exc}")
        return 2

    events: list[tuple[str, dict]] = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "smoke.db")
        service = TranslationService(engine, db)
        request = TranslateRequest(
            text=args.text, source_lang=args.src, target_lang=args.tgt,
            profile_id=args.profile, device=args.device,
        )
        service.run(request, lambda event, data=None: events.append((event, data or {})),
                    threading.Event())
        db.close()

    errors = [data for event, data in events if event == "error"]
    done = [data for event, data in events if event == "done"]
    result = {
        "device": resolved.device,
        "variant": str(resolved.variant),
        "warning": resolved.warning,
        "load_ms": getattr(engine.engine, "load_ms", None),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "error": errors[-1] if errors else None,
        "done": done[-1] if done else None,
        "source": args.text,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/smoke-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if errors:
        print(f"翻译失败: {errors[-1].get('message')}")
        return 1
    print(f"设备: {resolved.device}  变体: {resolved.variant}")
    print(f"加载: {(result['load_ms'] or 0):.0f} ms  总耗时: {result['elapsed_ms']} ms")
    print(f"译文: {done[-1].get('text', '')}")
    print(f"速度: {done[-1].get('tok_s', 0)} tok/s")
    engine.unload()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
