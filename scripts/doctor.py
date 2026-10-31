from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.config import ensure_dirs, resolve_data_dir, resolve_models_dir  # noqa: E402
from app.backend.engine.registry import EngineManager  # noqa: E402
from app.backend.services.diagnostics import collect_system_info, run_doctor  # noqa: E402
from app.backend.services.settings import load_settings  # noqa: E402
from app.backend.storage.db import Database  # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="ZC 离线翻译诊断")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--no-checks", action="store_true", help="只输出系统信息")
    args = parser.parse_args()

    ensure_dirs()
    db = None
    try:
        db = Database(resolve_data_dir() / "app.db")
        engine = EngineManager(resolve_models_dir())
        settings = load_settings(db)
        info = collect_system_info(db, engine)
        doctor = None if args.no_checks else run_doctor(db, engine, settings)

        if args.json:
            print(json.dumps({"system": info, "doctor": doctor}, ensure_ascii=False, indent=2))
        else:
            app = info["app"]
            ov = info["openvino"]
            print(f"ZC 离线翻译 {app['version']}  Python {app['python']}")
            print(f"OpenVINO {ov['runtime']}  GenAI {ov['genai']}")
            print(f"数据目录: {info['paths']['data']}")
            print(f"模型目录: {info['paths']['models']}")
            print("设备:")
            for device in ov["devices"]:
                print(f"  - {device['id']}: {device['name']}")
            if ov.get("npu_driver"):
                print(f"  - NPU 驱动: {ov['npu_driver']}")
            print("模型:")
            for model in info["models"].values():
                variants = ", ".join(model["variants"])
                print(f"  - {model['name']} [{variants}] {model['size_bytes'] / (1024 ** 3):.1f} GB")
            if doctor:
                print(f"诊断结论: {doctor['overall']}")
                for check in doctor["checks"]:
                    print(f"  [{check['status']:5}] {check['name']}: {check['detail']}")
            else:
                print(f"引擎: {info['engine']['state']}")
        return 1 if doctor and doctor["overall"] == "error" else 0
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
