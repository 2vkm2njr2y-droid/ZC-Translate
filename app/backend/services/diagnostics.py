"""System information and diagnostics exposed by the settings page."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from ..config import (
    APP_VERSION,
    MODEL_PROFILES,
    resolve_data_dir,
    resolve_log_dir,
    resolve_models_dir,
)
from ..engine.registry import EngineManager
from ..storage.db import Database


def _openvino_versions() -> tuple[str, str, str]:
    runtime = genai = ""
    try:
        import openvino as ov
        runtime = str(ov.__version__)
    except Exception:
        pass
    try:
        import openvino_genai as genai_module
        genai = str(genai_module.get_version())
    except Exception:
        pass
    return runtime, genai, platform.python_version()


def _webview2() -> bool:
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft" / "EdgeWebView" / "Application",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft" / "EdgeWebView" / "Application",
    ]
    return any(path.exists() for path in candidates)


def collect_system_info(db: Database, engine: EngineManager,
                        jobs: Any | None = None) -> dict[str, Any]:
    runtime, genai, python = _openvino_versions()
    devices = engine.resolver.describe()
    npu_driver = ""
    try:
        import openvino as ov
        core = ov.Core()
        if "NPU" in core.available_devices:
            npu_driver = str(core.get_property("NPU", "NPU_DRIVER_VERSION"))
    except Exception:
        pass
    data_dir = resolve_data_dir()
    packs = {key: pack.as_dict() for key, pack in engine.packs.items()}
    return {
        "app": {
            "name": "ZC 离线翻译",
            "version": APP_VERSION,
            "python": python,
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "openvino": {"runtime": runtime, "genai": genai, "devices": devices,
                     "npu_driver": npu_driver, "device_error": engine.resolver.error},
        "engine": engine.status(),
        "queue": jobs.counts() if jobs else {},
        "paths": {
            "data": str(data_dir),
            "models": str(resolve_models_dir()),
            "logs": str(resolve_log_dir()),
        },
        "models": packs,
        "profiles": list(MODEL_PROFILES.values()),
        "webview2": _webview2(),
        "db": {"path": str(db.path), "integrity": db.integrity_check()},
        "disk_free_gb": round(shutil.disk_usage(data_dir).free / (1024 ** 3), 1),
    }


def run_doctor(db: Database, engine: EngineManager,
               settings: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(check_id: str, name: str, status: str, detail: str = "") -> None:
        checks.append({"id": check_id, "name": name, "status": status, "detail": detail})

    runtime, genai, python = _openvino_versions()
    add("python", "Python 运行时", "ok" if sys.version_info >= (3, 11) else "error", python)
    add("openvino", "OpenVINO Runtime", "ok" if runtime else "error", runtime or "未安装")
    add("genai", "OpenVINO GenAI", "ok" if genai else "error", genai or "未安装")

    devices = {item["id"]: item for item in engine.resolver.describe()}
    for device, label in (("NPU", "Intel NPU"), ("GPU", "Intel GPU"), ("CPU", "CPU")):
        if device in devices:
            add(f"device-{device.lower()}", label, "ok", devices[device]["name"])
        else:
            status = "warn" if device in {"NPU", "GPU"} else "error"
            add(f"device-{device.lower()}", label, status, "未检测到设备")

    npu_driver = ""
    try:
        import openvino as ov
        core = ov.Core()
        if "NPU" in core.available_devices:
            npu_driver = str(core.get_property("NPU", "NPU_DRIVER_VERSION"))
    except Exception:
        pass
    add("npu-driver", "NPU 驱动", "ok" if npu_driver else "warn",
        npu_driver or "未读取到驱动版本")

    ready_packs = [pack for pack in engine.packs.values() if pack.ready]
    add("models", "翻译模型", "ok" if ready_packs else "error",
        "、".join(pack.name for pack in ready_packs) or "未找到可用模型")
    for profile in MODEL_PROFILES.values():
        model_id = str(profile["model_id"])
        pack = engine.packs.get(model_id)
        if not pack:
            add(f"model-{model_id}", str(profile["name"]),
                "warn" if profile.get("optional") else "error", "未安装")
        elif not pack.ready:
            add(f"model-{model_id}", str(profile["name"]), "error", pack.error or "不完整")
        else:
            add(f"model-{model_id}", str(profile["name"]), "ok",
                f"{len(pack.variants)} 个变体，{pack.size_bytes() / (1024 ** 3):.1f} GB")

    try:
        integrity = db.integrity_check()
        add("db", "本地数据库", "ok" if integrity == "ok" else "error", integrity)
    except Exception as exc:  # noqa: BLE001
        add("db", "本地数据库", "error", str(exc))

    data_dir = resolve_data_dir()
    try:
        probe = data_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        add("write", "数据目录可写", "ok", str(data_dir))
    except Exception as exc:  # noqa: BLE001
        add("write", "数据目录可写", "error", str(exc))

    free_gb = shutil.disk_usage(data_dir).free / (1024 ** 3)
    add("disk", "磁盘空间", "ok" if free_gb >= 5 else "warn", f"{free_gb:.1f} GB 可用")
    add("webview", "WebView2 运行时", "ok" if _webview2() else "warn",
        "已安装" if _webview2() else "未检测到，将回退默认浏览器")
    add("offline", "离线模式", "ok" if settings.get("offline_mode", True) else "warn",
        "已开启" if settings.get("offline_mode", True) else "已关闭（仅影响下载入口）")

    statuses = {check["status"] for check in checks}
    overall = "error" if "error" in statuses else ("warn" if "warn" in statuses else "ok")
    return {"ok": overall != "error", "overall": overall, "checks": checks}
