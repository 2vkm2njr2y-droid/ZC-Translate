"""Application configuration and filesystem layout.

The app is designed to run from the repository during development and from a
portable / installed folder in production.  Models are always external to the
executable so that they can be moved or copied without rebuilding.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ZC 离线翻译"
APP_ID = "zc-translate"
APP_VERSION = "0.1.2"
PROMPT_VERSION = "hymt2-v1"
DB_SCHEMA_VERSION = 1

# Hard limits for the local HTTP API.
MAX_TEXT_CHARS = 100_000
MAX_BLOCK_CHARS = 1_500
MAX_REQUEST_BYTES = 1_500_000

SUPPORTED_LANGUAGES = {
    "zh": {"name_zh": "中文", "name_en": "Chinese", "label": "中文"},
    "ja": {"name_zh": "日语", "name_en": "Japanese", "label": "日语"},
    "en": {"name_zh": "英语", "name_en": "English", "label": "英语"},
}

STYLE_PROMPTS = {
    "default": None,
    "formal": "正式、严谨的书面语",
    "casual": "自然、口语化的表达",
    "technical": "准确、简洁的技术文档风格",
    "literary": "保留原文语气与文学性的表达",
}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def repo_root() -> Path:
    """Project root during development, or the folder containing the exe."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else None


def _models_pointer(root: Path) -> Path | None:
    """Resolve an optional models-path.txt next to a frozen executable.

    The file makes an unpacked portable folder work when the user starts
    ``ZCTranslate.exe`` directly instead of the bundled launcher.  A relative
    path is resolved against the executable folder, and the first non-comment
    line wins.  A missing or invalid target falls back to the normal layout.
    """
    pointer = root / "models-path.txt"
    try:
        lines = pointer.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return None
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = root / path
        return path.resolve() if path.is_dir() else None
    return None


def portable_mode(root: Path | None = None) -> bool:
    root = root or repo_root()
    return (root / "portable.flag").exists()


def resolve_data_dir() -> Path:
    env = _env_path("ZC_DATA_DIR")
    if env:
        return env
    root = repo_root()
    if portable_mode(root):
        return root / "data"
    if not is_frozen() and (root / "models").exists():
        # Development checkout: keep everything inside the project.
        return root / "data"
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "ZCTranslate"


def resolve_models_dir() -> Path:
    env = _env_path("ZC_MODELS_DIR")
    if env:
        return env
    root = repo_root()
    candidate = root / "models"
    if candidate.exists() or not is_frozen():
        return candidate
    pointer = _models_pointer(root)
    if pointer is not None:
        return pointer
    return resolve_data_dir() / "models"


def resolve_log_dir() -> Path:
    env = _env_path("ZC_LOG_DIR")
    return env if env else resolve_data_dir() / "logs"


def resolve_frontend_dir() -> Path:
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "frontend"
    return Path(__file__).resolve().parents[1] / "frontend"


def ensure_dirs() -> None:
    for path in (resolve_data_dir(), resolve_models_dir(), resolve_log_dir(),
                 resolve_data_dir() / "cache", resolve_data_dir() / "backups"):
        path.mkdir(parents=True, exist_ok=True)


DEFAULT_SETTINGS: dict[str, object] = {
    "theme": "system",
    "target_lang": "zh",
    "source_lang": "auto",
    "profile_id": "balanced",
    "device": "auto",
    "style": "default",
    "glossary_id": "",
    "use_tm": True,
    "use_context": False,
    "refine": False,
    "split_mode": "auto",
    "temperature": 0.7,
    "top_p": 0.6,
    "top_k": 20,
    "repetition_penalty": 1.05,
    "rng_seed": 42,
    "max_new_tokens": 4096,
    "preload_model": True,
    "offline_mode": True,
    "selection_translate": False,
    "window": {"width": 1440, "height": 900, "split": 0.5, "sidebar": True},
}

# Model profiles exposed by the UI.  The actual availability is discovered by
# scanning the models directory at runtime.
MODEL_PROFILES: dict[str, dict[str, object]] = {
    "balanced": {
        "id": "balanced",
        "name": "Hy-MT2 1.8B",
        "model_id": "hymt2-1.8b",
        "params": "2.0B",
        "license": "Apache-2.0",
        "description": "默认档：速度快、占用低，适合 NPU / iGPU / CPU。",
        "devices": ["NPU", "GPU", "CPU"],
        "repo": "Tencent-Hunyuan/Hy-MT2-1.8B",
        "optional": False,
    },
    "quality": {
        "id": "quality",
        "name": "Hy-MT2 7B",
        "model_id": "hymt2-7b",
        "params": "8.0B",
        "license": "Apache-2.0",
        "description": "高精度档：质量优先，建议使用 GPU / CPU。",
        "devices": ["GPU", "CPU"],
        "repo": "Tencent-Hunyuan/Hy-MT2-7B",
        "optional": True,
    },
}


def profile_for_model(model_id: str) -> dict[str, object] | None:
    for profile in MODEL_PROFILES.values():
        if profile["model_id"] == model_id:
            return profile
    return None
