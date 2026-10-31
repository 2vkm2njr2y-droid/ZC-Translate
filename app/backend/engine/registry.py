"""Model discovery, device resolution and the single loaded engine instance."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import MODEL_PROFILES, profile_for_model, resolve_data_dir, resolve_models_dir
from ..engine.base import Engine, EngineError, GenerationOptions, GenerationResult, TokenCallback
from ..engine.openvino_engine import OpenVINOEngine

VARIANT_DEFAULT = "ov-int4"
VARIANT_NPU = "ov-int4-npu"


@dataclass
class ModelPack:
    id: str
    name: str
    path: Path
    variants: dict[str, Path] = field(default_factory=dict)
    license: str = ""
    params: str = ""
    repo: str = ""
    description: str = ""
    error: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.variants)

    def size_bytes(self) -> int:
        total = 0
        for variant in self.variants.values():
            for item in variant.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        return total

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": str(self.path),
            "variants": {key: str(value) for key, value in self.variants.items()},
            "license": self.license,
            "params": self.params,
            "repo": self.repo,
            "description": self.description,
            "ready": self.ready,
            "size_bytes": self.size_bytes(),
            "error": self.error,
        }


@dataclass
class ResolvedDevice:
    device: str
    variant: Path
    warning: str = ""


def _has_openvino_model(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(path.glob("*.xml"))


def scan_models(models_dir: str | Path | None = None) -> dict[str, ModelPack]:
    root = Path(models_dir) if models_dir else resolve_models_dir()
    packs: dict[str, ModelPack] = {}
    if not root.exists():
        return packs
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        pack_json = entry / "pack.json"
        pack = ModelPack(id=entry.name, name=entry.name, path=entry)
        if pack_json.exists():
            try:
                data = json.loads(pack_json.read_text(encoding="utf-8"))
                pack.id = str(data.get("id", entry.name))
                pack.name = str(data.get("name", entry.name))
                pack.license = str(data.get("license", ""))
                pack.params = str(data.get("params", ""))
                pack.repo = str(data.get("repo", ""))
                pack.description = str(data.get("description", ""))
                declared = data.get("variants", {})
                for key, meta in declared.items():
                    rel = meta.get("path") if isinstance(meta, dict) else meta
                    if not rel:
                        continue
                    path = entry / str(rel)
                    if _has_openvino_model(path):
                        pack.variants[key] = path
                    else:
                        pack.error = f"变体 {key} 缺少 OpenVINO 模型文件"
            except (OSError, json.JSONDecodeError) as exc:
                pack.error = f"pack.json 无法读取：{exc}"
        else:
            for key, dirname in (("default", VARIANT_DEFAULT), ("npu", VARIANT_NPU)):
                path = entry / dirname
                if _has_openvino_model(path):
                    pack.variants[key] = path
            if not pack.variants:
                continue
        if not pack.name or pack.name == pack.id:
            profile = profile_for_model(pack.id)
            if profile:
                pack.name = str(profile["name"])
                pack.license = pack.license or str(profile["license"])
                pack.params = pack.params or str(profile["params"])
                pack.repo = pack.repo or str(profile["repo"])
                pack.description = pack.description or str(profile["description"])
        packs[pack.id] = pack
    return packs


class DeviceResolver:
    def __init__(self) -> None:
        self.devices: list[str] = []
        self.names: dict[str, str] = {}
        self.error = ""
        try:
            import openvino as ov

            core = ov.Core()
            self.devices = list(core.available_devices)
            for device in self.devices:
                try:
                    self.names[device] = str(core.get_property(device, "FULL_DEVICE_NAME"))
                except Exception:
                    self.names[device] = device
        except Exception as exc:  # noqa: BLE001 - app must start without OpenVINO
            self.error = str(exc)

    def has(self, device: str) -> bool:
        return any(item == device or item.startswith(device + ".") for item in self.devices)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {"id": device, "name": self.names.get(device, device), "available": True}
            for device in self.devices
        ]

    def candidates(self, profile_id: str, requested: str,
                   packs: dict[str, ModelPack]) -> list[tuple[ModelPack, ResolvedDevice]]:
        """Return load candidates in fallback order.

        Explicit NPU never silently falls back.  GPU and auto may fall back to
        CPU; auto prefers NPU for the 1.8B profile and GPU for 7B.
        """
        if requested == "auto":
            order = ["NPU", "GPU", "CPU"] if profile_id == "balanced" else ["GPU", "CPU"]
        elif requested == "GPU":
            order = ["GPU", "CPU"]
        elif requested == "NPU":
            order = ["NPU"]
        else:
            order = ["CPU"]

        resolved: list[tuple[ModelPack, ResolvedDevice]] = []
        errors: list[str] = []
        for device in order:
            try:
                resolved.append(self.resolve(profile_id, device, packs))
            except EngineError as exc:
                errors.append(str(exc))
        if not resolved:
            raise EngineError("；".join(errors) or "没有可用设备")
        return resolved

    def resolve(self, profile_id: str, requested: str,
                packs: dict[str, ModelPack]) -> tuple[ModelPack, ResolvedDevice]:
        profile = MODEL_PROFILES.get(profile_id) or MODEL_PROFILES["balanced"]
        model_id = str(profile["model_id"])
        pack = packs.get(model_id)
        if pack is None:
            raise EngineError(f"未找到模型 {model_id}，请先运行“准备模型.bat”。")
        if not pack.ready:
            raise EngineError(pack.error or f"模型 {pack.id} 不完整。")
        if requested == "auto":
            if profile_id == "balanced" and "npu" in pack.variants and self.has("NPU"):
                return pack, ResolvedDevice("NPU", pack.variants["npu"])
            if "default" in pack.variants and self.has("GPU"):
                return pack, ResolvedDevice("GPU", pack.variants["default"])
            if "default" in pack.variants:
                warning = "" if self.has("CPU") else "未检测到 GPU/NPU，尝试使用 CPU。"
                return pack, ResolvedDevice("CPU", pack.variants["default"], warning)
            raise EngineError("没有可用于 CPU/GPU 的模型变体。")

        if requested == "NPU":
            if profile_id != "balanced":
                raise EngineError("7B 模型不建议在 NPU 上运行，请选择 GPU 或 CPU。")
            if "npu" not in pack.variants:
                raise EngineError("该模型缺少 NPU 变体（ov-int4-npu）。")
            if not self.has("NPU"):
                raise EngineError("未检测到 NPU 设备，请检查 Intel NPU 驱动。")
            return pack, ResolvedDevice("NPU", pack.variants["npu"])
        if requested == "GPU":
            if "default" not in pack.variants:
                raise EngineError("该模型缺少默认变体（ov-int4）。")
            if not self.has("GPU"):
                raise EngineError("未检测到 GPU 设备。")
            return pack, ResolvedDevice("GPU", pack.variants["default"])
        if requested == "CPU":
            if "default" not in pack.variants:
                raise EngineError("该模型缺少默认变体（ov-int4）。")
            return pack, ResolvedDevice("CPU", pack.variants["default"])
        raise EngineError(f"未知设备：{requested}")


class EngineManager:
    def __init__(self, models_dir: str | Path | None = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else resolve_models_dir()
        self.resolver = DeviceResolver()
        self.packs: dict[str, ModelPack] = {}
        self.engine: Engine | None = None
        self.pack: ModelPack | None = None
        self.resolved: ResolvedDevice | None = None
        self.state = "idle"
        self.last_error = ""
        self._load_lock = threading.Lock()
        self._generation_lock = threading.Lock()
        self.scan()

    def scan(self) -> dict[str, ModelPack]:
        self.packs = scan_models(self.models_dir)
        return self.packs

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "model_id": self.pack.id if self.pack else None,
            "model_name": self.pack.name if self.pack else None,
            "device": self.resolved.device if self.resolved else None,
            "variant": str(self.resolved.variant) if self.resolved else None,
            "load_ms": getattr(self.engine, "load_ms", None),
            "last_error": self.last_error,
            "devices": self.resolver.describe(),
            "device_error": self.resolver.error,
        }

    def ensure_loaded(self, profile_id: str, device: str = "auto",
                      on_status: Callable[[str], None] | None = None) -> ResolvedDevice:
        candidates = self.resolver.candidates(profile_id, device, self.packs)
        with self._load_lock:
            for index, (candidate_pack, resolved) in enumerate(candidates):
                if (self.engine is not None and self.resolved is not None
                        and self.pack is not None
                        and self.pack.id == candidate_pack.id
                        and self.resolved.variant == resolved.variant
                        and self.resolved.device == resolved.device):
                    if self.state != "ready":
                        self.state = "ready"
                    return self.resolved
                self.state = "loading"
                self.last_error = ""
                if on_status:
                    suffix = "" if not resolved.warning else f"；{resolved.warning}"
                    on_status(f"正在加载 {candidate_pack.name}（{resolved.device}）…{suffix}")
                cache_dir = str(resolve_data_dir() / "cache" / "ov" / candidate_pack.id)
                try:
                    engine = OpenVINOEngine()
                    engine.load(str(resolved.variant), resolved.device, cache_dir)
                    self.engine = engine
                    self.pack = candidate_pack
                    self.resolved = resolved
                    self.state = "ready"
                    if index > 0:
                        self.resolved.warning = f"首选设备不可用，已回退到 {resolved.device}"
                    if on_status:
                        on_status(f"模型已加载（{resolved.device}，{engine.load_ms:.0f} ms）")
                    return self.resolved
                except Exception as exc:  # noqa: BLE001
                    self.engine = None
                    self.pack = candidate_pack
                    self.last_error = str(exc)
                    if on_status:
                        on_status(f"{resolved.device} 加载失败：{exc}")
            self.state = "error"
            raise EngineError(f"加载模型失败：{self.last_error}")

    def preload(self, profile_id: str = "balanced", device: str = "auto") -> None:
        def worker() -> None:
            try:
                self.ensure_loaded(profile_id, device)
            except Exception:
                pass

        threading.Thread(target=worker, name="model-preload", daemon=True).start()

    def generate(self, messages: list[dict], options: GenerationOptions,
                 on_token: TokenCallback, cancel_event: threading.Event) -> GenerationResult:
        if self.engine is None or self.resolved is None or self.pack is None:
            raise EngineError("模型尚未加载")
        with self._generation_lock:
            if cancel_event.is_set():
                from ..engine.base import GenerationCancelled
                raise GenerationCancelled("已取消")
            prompt = self.engine.apply_chat_template(messages)
            return self.engine.generate(prompt, options, on_token, cancel_event)

    def count_tokens(self, text: str) -> int:
        if self.engine is None:
            return max(1, len(text) // 2)
        return self.engine.count_tokens(text)

    def unload(self) -> None:
        with self._load_lock:
            if self.engine is not None:
                self.engine.unload()
            self.engine = None
            self.pack = None
            self.resolved = None
            self.state = "idle"
