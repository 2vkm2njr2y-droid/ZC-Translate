from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.config import resolve_frontend_dir  # noqa: E402
from app.backend.engine.registry import EngineManager  # noqa: E402
from app.backend.pipeline.translator import TranslationService  # noqa: E402
from app.backend.schemas import TranslateRequest  # noqa: E402
from app.backend.storage.db import Database  # noqa: E402


def static_scan() -> list[str]:
    hits: list[str] = []
    frontend = resolve_frontend_dir()
    pattern = re.compile(r"https?://[^\s\"'<>)]+")
    for path in frontend.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".js", ".css", ".html", ".json"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(text):
                url = match.group(0)
                if "127.0.0.1" in url or "localhost" in url:
                    continue
                if url.startswith("http://www.w3.org/"):
                    # SVG/XML namespace identifiers are not network requests.
                    continue
                hits.append(f"{path.relative_to(frontend)}: {url}")
    return hits


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="验证运行时完全不访问网络")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--text", default="离线检查：缓存目录缺失时应该自动重建。")
    args = parser.parse_args()

    external = static_scan()
    if external:
        print("前端存在外部 URL：")
        for item in external:
            print("  " + item)
        return 1

    engine = EngineManager()
    try:
        resolved = engine.ensure_loaded("balanced", args.device)
    except Exception as exc:  # noqa: BLE001
        print(f"模型加载失败，无法做运行期离线检查: {exc}")
        return 2

    original_connect = socket.socket.connect

    def blocked(self, address):  # noqa: ANN001
        raise OSError("network access blocked by offline check")

    socket.socket.connect = blocked  # type: ignore[assignment]
    try:
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "offline.db")
            service = TranslationService(engine, db)
            request = TranslateRequest(
                text=args.text, source_lang="zh", target_lang="en",
                profile_id="balanced", device=args.device,
            )
            service.run(request, lambda event, data=None: events.append((event, data or {})),
                        threading.Event())
            db.close()
    finally:
        socket.socket.connect = original_connect  # type: ignore[assignment]

    errors = [data for event, data in events if event == "error"]
    done = [data for event, data in events if event == "done"]
    if errors or not done:
        print("断网翻译失败：")
        print(json.dumps(errors[-1] if errors else {}, ensure_ascii=False, indent=2))
        return 1
    print(f"离线检查通过：{resolved.device}，无外部 URL，断网后翻译仍成功。")
    print(f"译文：{done[-1]['text']}")
    engine.unload()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
