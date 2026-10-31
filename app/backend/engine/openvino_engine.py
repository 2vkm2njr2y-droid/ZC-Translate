"""OpenVINO GenAI LLMPipeline adapter.

The pipeline is used in text mode.  Chat templates are applied explicitly with
the model tokenizer (the same template the model was trained with), and
generation is streamed through a Python callback.
"""

from __future__ import annotations

import gc
import time
from threading import Event
from typing import Any

import openvino_genai as ov_genai

from .base import (
    EngineError,
    GenerationCancelled,
    GenerationOptions,
    GenerationResult,
    TokenCallback,
)


def _metric(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "mean"):
        try:
            return float(value.mean)
        except Exception:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class OpenVINOEngine:
    def __init__(self) -> None:
        self.pipe: ov_genai.LLMPipeline | None = None
        self.tokenizer: ov_genai.Tokenizer | None = None
        self.device: str = ""
        self.model_dir: str = ""
        self.load_ms: float = 0.0

    # ------------------------------------------------------------------ load
    def load(self, model_dir: str, device: str, cache_dir: str | None = None) -> float:
        self.unload()
        started = time.perf_counter()
        kwargs: dict[str, Any] = {}
        if cache_dir:
            kwargs["CACHE_DIR"] = cache_dir
        try:
            self.pipe = ov_genai.LLMPipeline(str(model_dir), device, **kwargs)
        except TypeError:
            # Older bindings do not accept arbitrary properties as kwargs.
            self.pipe = ov_genai.LLMPipeline(str(model_dir), device)
        self.tokenizer = self.pipe.get_tokenizer()
        self.device = device
        self.model_dir = str(model_dir)
        self.load_ms = (time.perf_counter() - started) * 1000.0
        return self.load_ms

    def unload(self) -> None:
        self.pipe = None
        self.tokenizer = None
        gc.collect()

    @property
    def loaded(self) -> bool:
        return self.pipe is not None

    # ------------------------------------------------------------- tokenizer
    def apply_chat_template(self, messages: list[dict]) -> str:
        if self.tokenizer is None:
            raise EngineError("模型尚未加载")
        try:
            return self.tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        except Exception:
            # ChatML fallback, matching Hunyuan's template.
            content = messages[-1]["content"] if messages else ""
            return f"<|im_start|>user\n{content}<|im_end|>\n<|im_start|>assistant\n"

    def count_tokens(self, text: str) -> int:
        if self.tokenizer is None:
            return max(1, len(text) // 2)
        try:
            encoded = self.tokenizer.encode(text)
            tensor = getattr(encoded, "input_ids", encoded)
            shape = getattr(tensor, "shape", None)
            if shape:
                return int(shape[-1])
        except Exception:
            pass
        return max(1, len(text) // 2)

    # ------------------------------------------------------------- generate
    def generate(self, prompt: str, options: GenerationOptions,
                 on_token: TokenCallback, cancel_event: Event) -> GenerationResult:
        if self.pipe is None:
            raise EngineError("模型尚未加载")

        config = ov_genai.GenerationConfig()
        config.max_new_tokens = int(options.max_new_tokens)
        config.temperature = float(options.temperature)
        config.top_p = float(options.top_p)
        config.top_k = int(options.top_k)
        config.repetition_penalty = float(options.repetition_penalty)
        config.do_sample = bool(options.do_sample)
        config.rng_seed = int(options.rng_seed)
        # The prompt is already templated by apply_chat_template().
        config.apply_chat_template = False

        started = time.perf_counter()
        first_token: float | None = None
        chunks: list[str] = []

        def callback(piece: str) -> bool:
            nonlocal first_token
            if cancel_event.is_set():
                return True
            if first_token is None:
                first_token = time.perf_counter()
            chunks.append(piece)
            try:
                on_token(piece)
            except Exception:
                # A UI/queue failure must not kill generation silently.
                pass
            return False

        try:
            result = self.pipe.generate(prompt, config, callback)
        except Exception as exc:  # noqa: BLE001 - surface a clear engine error
            if cancel_event.is_set():
                raise GenerationCancelled("已取消") from exc
            raise EngineError(f"{self.device} 推理失败：{exc}") from exc

        total_ms = (time.perf_counter() - started) * 1000.0
        text = "".join(chunks)
        if not text and isinstance(result, str):
            text = result
        if not text:
            texts = getattr(result, "texts", None) or []
            text = texts[0] if texts else ""
        gen_tokens = 0
        ttft_ms = 0.0
        metrics = getattr(result, "perf_metrics", None)
        if metrics is not None:
            gen_tokens = int(metrics.get_num_generated_tokens() or 0)
            metric_ttft = _metric(metrics.get_ttft())
            if metric_ttft is not None:
                ttft_ms = metric_ttft
        if not gen_tokens and self.tokenizer is not None and text:
            try:
                encoded = self.tokenizer.encode(text)
                tensor = getattr(encoded, "input_ids", encoded)
                shape = getattr(tensor, "shape", None)
                if shape:
                    gen_tokens = int(shape[-1])
            except Exception:
                pass
        if not gen_tokens:
            gen_tokens = max(1, len(text) // 2)
        if ttft_ms <= 0:
            ttft_ms = ((first_token - started) * 1000.0) if first_token else total_ms
        generation_ms = max(1.0, total_ms - ttft_ms)
        tok_s = gen_tokens / (generation_ms / 1000.0)
        cancelled = cancel_event.is_set()
        return GenerationResult(
            text=text,
            device=self.device,
            model_id=self.model_dir,
            gen_tokens=gen_tokens,
            ttft_ms=ttft_ms,
            total_ms=total_ms,
            tok_s=tok_s,
            finish_reason="cancelled" if cancelled else "stop",
            cancelled=cancelled,
        )
