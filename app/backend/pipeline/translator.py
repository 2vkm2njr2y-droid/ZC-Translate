"""End-to-end translation orchestration with streaming and validation."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import traceback
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..config import MODEL_PROFILES, PROMPT_VERSION, SUPPORTED_LANGUAGES
from ..engine.base import EngineError, GenerationCancelled, GenerationOptions
from ..engine.registry import EngineManager
from ..schemas import ScreenshotTranslateRequest, TranslateRequest
from ..storage.db import Database
from . import langid, postprocess, prompts
from .glossary import GlossaryTerm, glossary_hash, select_terms, verify_terms
from .placeholders import protect
from .splitter import Block, join_blocks, split_blocks

logger = logging.getLogger(__name__)
Emit = Callable[[str, dict[str, Any] | None], None]


class LanguageError(EngineError):
    """Language detection or direction validation failed."""

    code = "LANG_UNKNOWN"


class SameLanguageError(LanguageError):
    code = "SAME_LANGUAGE"


class UnknownLanguageError(LanguageError):
    code = "LANG_UNKNOWN"


@dataclass
class TranslationContext:
    src_lang: str
    detected_lang: str | None
    settings: dict[str, Any]
    profile_id: str
    device: str
    pack: Any
    resolved: Any
    terms: list[GlossaryTerm]
    ghash: str
    options_base: GenerationOptions
    warnings: list[str] = field(default_factory=list)


@dataclass
class LineOutcome:
    text: str = ""
    warnings: list[str] = field(default_factory=list)
    critical: bool = False
    tm_hit: bool = False
    glossary_hits: int = 0
    glossary_misses: list[str] = field(default_factory=list)
    gen_tokens: int = 0
    last_gen_tokens: int = 0
    tok_s: float = 0.0
    ttft_ms: float = 0.0
    gen_ms: float = 0.0
    cancelled: bool = False


def _normalize_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


class TranslationService:
    def __init__(self, engine: EngineManager, db: Database) -> None:
        self.engine = engine
        self.db = db

    # ------------------------------------------------------------------ public
    def run(self, req: TranslateRequest, emit: Emit, cancel: threading.Event) -> None:
        started = time.perf_counter()
        translated: dict[int, str] = {}
        warnings: list[str] = []
        blocks: list[Block] = []
        gen_tokens_total = 0
        gen_ms_total = 0.0
        tm_hits = 0
        history_id = ""
        status = "completed"
        error_message = ""
        detected: str | None = None
        src_lang = req.source_lang
        ctx: TranslationContext | None = None

        try:
            src_lang, detected = self._resolve_language(req, req.text)
            ctx = self._prepare_context(req, src_lang, detected, emit)
            blocks = split_blocks(req.text, req.split_mode)
            if not blocks:
                raise EngineError("没有可翻译的文本。")
            emit("meta", {
                "job_id": "",
                "src_lang": src_lang,
                "detected_lang": detected,
                "tgt_lang": req.target_lang,
                "profile_id": ctx.profile_id,
                "model": ctx.pack.name if ctx.pack else "",
                "device": ctx.resolved.device,
                "device_warning": ctx.resolved.warning,
                "prompt_version": PROMPT_VERSION,
                "blocks": [block.as_dict() for block in blocks],
            })

            warnings.extend(ctx.warnings)
            prev_source = ""
            prev_target = ""

            for block in blocks:
                if cancel.is_set():
                    status = "cancelled"
                    break
                if not block.translate or not block.text.strip():
                    translated[block.index] = block.text
                    emit("block_start", {"block_id": block.index, "source": block.text,
                                         "kind": block.kind})
                    emit("block_done", {
                        "block_id": block.index,
                        "text": block.text,
                        "tm_hit": False,
                        "warnings": [],
                        "glossary_hits": 0,
                        "gen_tokens": 0,
                        "tok_s": 0.0,
                        "ttft_ms": 0.0,
                    })
                    prev_source, prev_target = block.text, block.text
                    continue

                background = ""
                if req.use_context and prev_source and prev_target and len(prev_source) < 500:
                    if prompts.use_chinese_prompt(src_lang, req.target_lang):
                        background = f"上一段原文：{prev_source}\n上一段译文：{prev_target}"
                    else:
                        background = (f"Previous source: {prev_source}\n"
                                      f"Previous translation: {prev_target}")

                block_id = block.index
                outcome = self._translate_line(
                    block.text,
                    ctx,
                    req,
                    cancel,
                    on_attempt=lambda bid=block_id, source=block.text, kind=block.kind: emit(
                        "block_start", {"block_id": bid, "source": source, "kind": kind}
                    ),
                    on_retry=lambda reason, bid=block_id: emit(
                        "block_reset", {"block_id": bid, "reason": reason}
                    ),
                    on_token=lambda piece, bid=block_id: emit(
                        "delta", {"block_id": bid, "text": piece}
                    ),
                    background=background,
                )
                gen_tokens_total += outcome.gen_tokens
                gen_ms_total += outcome.gen_ms

                if outcome.cancelled:
                    if outcome.text:
                        translated[block_id] = outcome.text
                        emit("block_done", {
                            "block_id": block_id,
                            "text": outcome.text,
                            "tm_hit": False,
                            "warnings": outcome.warnings + ["已取消"],
                            "glossary_hits": outcome.glossary_hits,
                            "gen_tokens": outcome.last_gen_tokens,
                            "tok_s": outcome.tok_s,
                            "ttft_ms": outcome.ttft_ms,
                        })
                    status = "cancelled"
                    break

                translated[block_id] = outcome.text
                block_warnings = list(dict.fromkeys(outcome.warnings))
                for warning in block_warnings:
                    warnings.append(f"块 {block_id + 1}：{warning}")

                if outcome.tm_hit:
                    tm_hits += 1
                    emit("block_start", {"block_id": block_id, "source": block.text,
                                         "kind": block.kind})
                    emit("block_done", {
                        "block_id": block_id,
                        "text": outcome.text,
                        "tm_hit": True,
                        "warnings": [],
                        "glossary_hits": outcome.glossary_hits,
                        "gen_tokens": 0,
                        "tok_s": 0.0,
                        "ttft_ms": 0.0,
                    })
                else:
                    emit("block_done", {
                        "block_id": block_id,
                        "text": outcome.text,
                        "tm_hit": False,
                        "warnings": block_warnings,
                        "glossary_hits": outcome.glossary_hits,
                        "glossary_misses": outcome.glossary_misses,
                        "gen_tokens": outcome.last_gen_tokens,
                        "tok_s": outcome.tok_s,
                        "ttft_ms": outcome.ttft_ms,
                    })
                prev_source, prev_target = block.text, outcome.text

        except GenerationCancelled:
            status = "cancelled"
            error_message = "已取消"
        except EngineError as exc:
            status = "error"
            error_message = str(exc)
            logger.error("Translation failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error_message = f"内部错误：{exc}"
            logger.error("Translation crashed: %s\n%s", exc, traceback.format_exc())

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        result_text = join_blocks(blocks, translated) if blocks else ""
        gen_tokens_total = max(0, gen_tokens_total)
        avg_tok_s = (gen_tokens_total / (gen_ms_total / 1000.0)) if gen_ms_total else 0.0
        device = ctx.resolved.device if ctx and ctx.resolved else ""
        model = ctx.pack.name if ctx and ctx.pack else ""
        profile = (ctx.profile_id if ctx else
                   (req.profile_id or self._settings().get("profile_id", "balanced")))

        try:
            history_id = self.db.add_history(
                kind="text",
                src_lang=src_lang if src_lang != "auto" else None,
                detected_lang=detected,
                tgt_lang=req.target_lang,
                profile=profile,
                device=device,
                source_text=req.text,
                result_text=result_text,
                status=status,
                duration_ms=elapsed_ms,
                gen_tokens=gen_tokens_total,
                warnings=warnings[:80],
                error=error_message or None,
            )
        except Exception:
            logger.exception("Failed to write history")

        if status == "error":
            emit("error", {
                "code": "GENERATION_FAILED",
                "message": error_message or "翻译失败",
                "history_id": history_id,
            })
        else:
            emit("done", {
                "status": status,
                "history_id": history_id,
                "elapsed_ms": elapsed_ms,
                "gen_tokens": gen_tokens_total,
                "tok_s": round(avg_tok_s, 1),
                "device": device,
                "model": model,
                "cancelled": status == "cancelled",
                "warnings": warnings[:80],
                "tm_hits": tm_hits,
                "text": result_text,
            })

    # ------------------------------------------------------- screenshot lines
    def run_lines(self, req: ScreenshotTranslateRequest, emit: Emit,
                  cancel: threading.Event) -> None:
        """Translate OCR lines independently while preserving their order."""
        started = time.perf_counter()
        lines = list(req.lines)
        results = ["" for _ in lines]
        warnings: list[str] = []
        status = "completed"
        error_message = ""
        history_id = ""
        src_lang = req.source_lang
        detected: str | None = None
        ctx: TranslationContext | None = None
        gen_tokens_total = 0
        gen_ms_total = 0.0
        tm_hits = 0

        try:
            src_lang, detected = self._resolve_language(req, "\n".join(lines))
            ctx = self._prepare_context(req, src_lang, detected, emit)
            emit("meta", {
                "src_lang": src_lang,
                "detected_lang": detected,
                "tgt_lang": req.target_lang,
                "profile_id": ctx.profile_id,
                "model": ctx.pack.name if ctx.pack else "",
                "device": ctx.resolved.device,
                "device_warning": ctx.resolved.warning,
                "prompt_version": PROMPT_VERSION,
                "count": len(lines),
            })
            warnings.extend(ctx.warnings)

            for index, line in enumerate(lines):
                if cancel.is_set():
                    status = "cancelled"
                    break
                emit("item_start", {"index": index})
                outcome = self._translate_line(
                    line,
                    ctx,
                    req,
                    cancel,
                    on_retry=lambda reason, item=index: emit(
                        "item_reset", {"index": item, "reason": reason}
                    ),
                    on_token=lambda piece, item=index: emit(
                        "item_delta", {"index": item, "text": piece}
                    ),
                )
                gen_tokens_total += outcome.gen_tokens
                gen_ms_total += outcome.gen_ms
                if outcome.cancelled:
                    if outcome.text:
                        results[index] = outcome.text
                        emit("item_done", {
                            "index": index,
                            "text": outcome.text,
                            "tm_hit": outcome.tm_hit,
                            "warnings": outcome.warnings + ["已取消"],
                            "glossary_hits": outcome.glossary_hits,
                            "glossary_misses": outcome.glossary_misses,
                            "gen_tokens": outcome.gen_tokens,
                            "tok_s": outcome.tok_s,
                            "ttft_ms": outcome.ttft_ms,
                        })
                    status = "cancelled"
                    break

                text = outcome.text
                item_warnings = list(dict.fromkeys(outcome.warnings))
                if len(line) < 80:
                    # Short UI labels naturally become shorter in Chinese/Japanese;
                    # the generic length heuristic is too noisy for screenshot lines.
                    item_warnings = [
                        warning for warning in item_warnings
                        if not warning.startswith("译文明显偏短")
                    ]
                if not text:
                    text = line
                    item_warnings.append("未得到译文，已保留原文。")
                results[index] = text
                for warning in item_warnings:
                    warnings.append(f"第 {index + 1} 段：{warning}")
                if outcome.tm_hit:
                    tm_hits += 1
                emit("item_done", {
                    "index": index,
                    "text": text,
                    "tm_hit": outcome.tm_hit,
                    "warnings": item_warnings,
                    "glossary_hits": outcome.glossary_hits,
                    "glossary_misses": outcome.glossary_misses,
                    "gen_tokens": outcome.gen_tokens,
                    "tok_s": outcome.tok_s,
                    "ttft_ms": outcome.ttft_ms,
                })

        except SameLanguageError as exc:
            emit("error", {"code": "SAME_LANGUAGE", "message": str(exc)})
            return
        except UnknownLanguageError as exc:
            emit("error", {"code": "LANG_UNKNOWN", "message": str(exc)})
            return
        except EngineError as exc:
            status = "error"
            error_message = str(exc)
            logger.error("Screenshot translation failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error_message = f"内部错误：{exc}"
            logger.error("Screenshot translation crashed: %s\n%s", exc, traceback.format_exc())

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        gen_tokens_total = max(0, gen_tokens_total)
        avg_tok_s = (gen_tokens_total / (gen_ms_total / 1000.0)) if gen_ms_total else 0.0
        result_text = "\n".join(results)
        device = ctx.resolved.device if ctx and ctx.resolved else ""
        model = ctx.pack.name if ctx and ctx.pack else ""

        try:
            history_id = self.db.add_history(
                kind="screenshot",
                src_lang=src_lang if src_lang != "auto" else None,
                detected_lang=detected,
                tgt_lang=req.target_lang,
                profile=(ctx.profile_id if ctx else
                         (req.profile_id or self._settings().get("profile_id", "balanced"))),
                device=device,
                source_text="\n".join(lines),
                result_text=result_text,
                status=status,
                duration_ms=elapsed_ms,
                gen_tokens=gen_tokens_total,
                warnings=warnings[:80],
                error=error_message or None,
            )
        except Exception:
            logger.exception("Failed to write screenshot history")

        if status == "error":
            emit("error", {
                "code": "GENERATION_FAILED",
                "message": error_message or "截图翻译失败",
                "history_id": history_id,
            })
        else:
            emit("done", {
                "status": status,
                "history_id": history_id,
                "elapsed_ms": elapsed_ms,
                "gen_tokens": gen_tokens_total,
                "tok_s": round(avg_tok_s, 1),
                "device": device,
                "model": model,
                "cancelled": status == "cancelled",
                "warnings": warnings[:80],
                "tm_hits": tm_hits,
                "targets": results,
                "text": result_text,
            })

    def _resolve_language(self, req: TranslateRequest | ScreenshotTranslateRequest,
                         sample_text: str) -> tuple[str, str | None]:
        src_lang = req.source_lang
        detected: str | None = None
        if src_lang == "auto":
            guess = langid.detect_language(sample_text)
            detected = guess.lang
            if not detected:
                raise UnknownLanguageError("无法判断源语言，请手动选择中文、日语或英语。")
            src_lang = detected
        if src_lang not in SUPPORTED_LANGUAGES:
            raise EngineError(f"不支持的源语言：{src_lang}")
        if req.target_lang not in SUPPORTED_LANGUAGES:
            raise EngineError(f"不支持的目标语言：{req.target_lang}")
        if src_lang == req.target_lang:
            raise SameLanguageError("源语言与目标语言相同，请切换语言或交换方向。")
        return src_lang, detected

    def _prepare_context(self, req: TranslateRequest | ScreenshotTranslateRequest,
                         src_lang: str, detected: str | None,
                         emit: Emit) -> TranslationContext:
        settings = self._settings()
        profile_id = req.profile_id or str(settings.get("profile_id", "balanced"))
        if profile_id not in MODEL_PROFILES:
            profile_id = "balanced"
        device = req.device or "auto"

        emit("status", {"phase": "loading", "message": "正在准备模型…"})
        resolved = self.engine.ensure_loaded(
            profile_id,
            device,
            on_status=lambda message: emit("status", {"phase": "loading", "message": message}),
        )
        pack = self.engine.pack
        terms, ghash, glossary_warning = self._load_glossary(
            req.glossary_id, src_lang, req.target_lang
        )
        return TranslationContext(
            src_lang=src_lang,
            detected_lang=detected,
            settings=settings,
            profile_id=profile_id,
            device=device,
            pack=pack,
            resolved=resolved,
            terms=terms,
            ghash=ghash,
            options_base=self._options(settings, req),
            warnings=[glossary_warning] if glossary_warning else [],
        )

    def _translate_line(self, text: str, ctx: TranslationContext,
                        req: TranslateRequest | ScreenshotTranslateRequest,
                        cancel: threading.Event, *,
                        on_token: Callable[[str], None] | None = None,
                        on_retry: Callable[[str], None] | None = None,
                        on_attempt: Callable[[], None] | None = None,
                        background: str = "") -> LineOutcome:
        protected = protect(text)
        selected = select_terms(protected.masked, ctx.terms)
        source_key = _normalize_key(protected.masked)
        outcome = LineOutcome(glossary_hits=len(selected))

        tm_hit = None
        if req.use_tm and ctx.settings.get("use_tm", True):
            tm_hit = self.db.get_tm(
                ctx.src_lang, req.target_lang, ctx.profile_id, PROMPT_VERSION,
                ctx.ghash, source_key,
            )
        if tm_hit:
            outcome.text = tm_hit["target_text"]
            outcome.tm_hit = True
            return outcome

        prompt = prompts.build_prompt(
            text=protected.masked,
            src_lang=ctx.src_lang,
            tgt_lang=req.target_lang,
            terms=selected,
            style=req.style,
            placeholder_count=len(protected.mapping),
            background=background,
        )
        messages = prompt.messages()
        max_tokens = self._max_tokens(ctx.settings, protected.masked)
        base = ctx.options_base
        options = GenerationOptions(
            max_new_tokens=max_tokens,
            temperature=base.temperature,
            top_p=base.top_p,
            top_k=base.top_k,
            repetition_penalty=base.repetition_penalty,
            do_sample=base.do_sample,
            rng_seed=base.rng_seed,
        )

        attempts = 0
        result_text = ""
        block_warnings: list[str] = []
        glossary_misses: list[str] = []
        critical = False

        while attempts < 2:
            if cancel.is_set():
                outcome.cancelled = True
                break
            if attempts and on_retry:
                on_retry("译文校验未通过，正在重试…")
            if on_attempt:
                on_attempt()

            def emit_token(piece: str) -> None:
                if on_token:
                    on_token(piece)

            try:
                result = self.engine.generate(messages, options, emit_token, cancel)
            except GenerationCancelled:
                outcome.cancelled = True
                break

            cleaned = postprocess.clean_output(result.text, req.target_lang)
            restored = protected.restore(cleaned).strip()
            result_text = restored
            checks = postprocess.check_output(text, restored, req.target_lang, protected)
            block_warnings = list(checks.warnings)
            glossary_misses = verify_terms(restored, selected)
            if glossary_misses:
                block_warnings.append("术语未命中：" + "；".join(glossary_misses[:5]))

            critical = (not restored) or bool(checks.placeholders_missing) \
                or bool(checks.placeholders_duplicated)
            outcome.gen_tokens += result.gen_tokens
            outcome.last_gen_tokens = result.gen_tokens
            outcome.gen_ms += max(1.0, result.total_ms - result.ttft_ms)
            outcome.tok_s = round(result.tok_s, 1)
            outcome.ttft_ms = round(result.ttft_ms, 1)

            if result.cancelled:
                outcome.cancelled = True
                break
            if not critical and not glossary_misses:
                break
            if attempts == 0:
                messages[0]["content"] += (
                    "\n\n请仔细核对原文，确保译文完整、准确，"
                    "保留所有占位符、数字、URL 和指定术语；只输出译文。"
                )
                options.do_sample = False
                options.temperature = 0.0
            attempts += 1

        outcome.text = result_text
        outcome.warnings = block_warnings
        outcome.critical = critical
        outcome.glossary_misses = glossary_misses
        if not outcome.cancelled and critical:
            outcome.warnings.append("自动校验未通过，已保留最佳结果，请人工复核。")
        if not outcome.cancelled:
            outcome.warnings = list(dict.fromkeys(outcome.warnings))
        if not critical and not outcome.cancelled and not cancel.is_set():
            try:
                self.db.put_tm(
                    ctx.src_lang, req.target_lang, ctx.profile_id, PROMPT_VERSION,
                    ctx.ghash, source_key, result_text,
                )
            except Exception:
                logger.exception("Failed to write translation memory")
        return outcome

    # ---------------------------------------------------------------- helpers
    def _settings(self) -> dict[str, Any]:
        from ..services.settings import load_settings
        return load_settings(self.db)

    def _load_glossary(self, glossary_id: str | None, src_lang: str,
                       tgt_lang: str) -> tuple[list[GlossaryTerm], str, str]:
        if not glossary_id:
            return [], "", ""
        glossary = self.db.get_glossary(glossary_id)
        if not glossary:
            return [], "", "所选术语库不存在，已忽略。"
        rows = self.db.list_terms(glossary_id)
        terms = [
            GlossaryTerm(
                source=row["source"],
                target=row["target"],
                case_sensitive=bool(row["case_sensitive"]),
                note=row["note"],
            )
            for row in rows
        ]
        if glossary["src_lang"] == src_lang and glossary["tgt_lang"] == tgt_lang:
            return terms, glossary_hash(terms, glossary_id), ""
        if (glossary["bidirectional"] and glossary["src_lang"] == tgt_lang
                and glossary["tgt_lang"] == src_lang):
            reversed_terms = [GlossaryTerm(source=term.target, target=term.source,
                                           case_sensitive=term.case_sensitive,
                                           note=term.note) for term in terms]
            return reversed_terms, glossary_hash(reversed_terms, glossary_id), ""
        return [], "", "术语库方向与当前翻译方向不一致，已忽略。"

    def _options(self, settings: dict[str, Any],
                 req: TranslateRequest | ScreenshotTranslateRequest) -> GenerationOptions:
        temperature = float(settings.get("temperature", 0.7))
        do_sample = temperature > 0.01
        return GenerationOptions(
            max_new_tokens=int(settings.get("max_new_tokens", 4096)),
            temperature=temperature,
            top_p=float(settings.get("top_p", 0.6)),
            top_k=int(settings.get("top_k", 20)),
            repetition_penalty=float(settings.get("repetition_penalty", 1.05)),
            do_sample=do_sample,
            rng_seed=int(settings.get("rng_seed", 42)),
        )

    def _max_tokens(self, settings: dict[str, Any], text: str) -> int:
        try:
            source_tokens = self.engine.count_tokens(text)
        except Exception:
            source_tokens = max(1, len(text) // 2)
        requested = max(128, source_tokens * 2 + 128)
        return int(min(int(settings.get("max_new_tokens", 4096)), max(128, requested)))
