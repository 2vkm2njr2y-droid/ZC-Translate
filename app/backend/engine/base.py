from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Protocol


class EngineError(RuntimeError):
    """A model load or generation failure with a user-actionable message."""


class GenerationCancelled(EngineError):
    """Raised when the user cancels a generation."""


@dataclass
class GenerationOptions:
    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.6
    top_k: int = 20
    repetition_penalty: float = 1.05
    do_sample: bool = True
    rng_seed: int = 42


@dataclass
class GenerationResult:
    text: str
    device: str
    model_id: str
    gen_tokens: int
    ttft_ms: float
    total_ms: float
    tok_s: float
    finish_reason: str = "stop"
    cancelled: bool = False


TokenCallback = Callable[[str], None]


class Engine(Protocol):
    def load(self, model_dir: str, device: str, cache_dir: str | None = None) -> float: ...
    def unload(self) -> None: ...
    def apply_chat_template(self, messages: list[dict]) -> str: ...
    def count_tokens(self, text: str) -> int: ...
    def generate(self, prompt: str, options: GenerationOptions,
                 on_token: TokenCallback, cancel_event: Event) -> GenerationResult: ...
