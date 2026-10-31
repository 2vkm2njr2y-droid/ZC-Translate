"""Offline microphone capture and speech recognition.

The service deliberately stops at speech-to-text.  Translation is still done
by :class:`TranslationService`, which keeps voice input consistent with text
input and preserves the existing local translation model.
"""

from __future__ import annotations

import logging
import os
import tarfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

try:  # Optional until the user installs the voice feature dependencies.
    import numpy as np
    import sherpa_onnx
    import sounddevice as sd
except ImportError:  # pragma: no cover - exercised on minimal installs
    np = None  # type: ignore[assignment]
    sherpa_onnx = None  # type: ignore[assignment]
    sd = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
PAUSE_SECONDS = 2.5
MAX_SPEECH_SECONDS = 60.0
MODEL_DIR_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
MODEL_ARCHIVE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
)
VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"


@dataclass
class SpeechSession:
    id: str
    mode: str
    started_at: float = field(default_factory=time.time)
    state: str = "starting"
    error: str = ""
    partial: str = ""
    partial_text: str = ""
    transcript: str = ""
    audio_seconds: float = 0.0
    next_seq: int = 0
    segments: list[dict[str, Any]] = field(default_factory=list)
    speech_chunks: list[Any] = field(default_factory=list)
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class SpeechService:
    """Own one local microphone session at a time."""

    def __init__(self, models_dir: Path) -> None:
        self.root = Path(models_dir) / "speech"
        self.model_dir = self.root / MODEL_DIR_NAME
        self.model_path = self.model_dir / "model.int8.onnx"
        self.tokens_path = self.model_dir / "tokens.txt"
        self.vad_path = self.root / "silero_vad.onnx"
        self._lock = threading.RLock()
        self._session: SpeechSession | None = None
        self._download: dict[str, Any] = {"state": "idle", "progress": 0, "message": ""}

    # --------------------------------------------------------------- lifecycle
    def shutdown(self) -> None:
        with self._lock:
            session = self._session
        if session:
            session.stop_event.set()
            if session.thread and session.thread.is_alive():
                session.thread.join(timeout=2)

    # -------------------------------------------------------------- model state
    def model_status(self) -> dict[str, Any]:
        with self._lock:
            download = dict(self._download)
        installed = self.model_path.is_file() and self.tokens_path.is_file() and self.vad_path.is_file()
        dependencies = sherpa_onnx is not None and sd is not None and np is not None
        return {
            "installed": installed,
            "ready": installed and dependencies,
            "dependencies": dependencies,
            "model": MODEL_DIR_NAME,
            "model_path": str(self.model_path),
            "download": download,
            "pause_seconds": PAUSE_SECONDS,
            "languages": ["zh", "ja", "en"],
        }

    def start_download(self) -> dict[str, Any]:
        with self._lock:
            if self._download.get("state") == "downloading":
                return dict(self._download)
            if self.model_path.is_file() and self.tokens_path.is_file() and self.vad_path.is_file():
                self._download = {"state": "ready", "progress": 100, "message": "语音模型已就绪"}
                return dict(self._download)
            self._download = {"state": "downloading", "progress": 0, "message": "准备下载语音模型…"}
        threading.Thread(target=self._download_worker, name="speech-model-download", daemon=True).start()
        return self.model_status()["download"]

    def _set_download(self, **updates: Any) -> None:
        with self._lock:
            self._download.update(updates)

    def _download_worker(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            archive = self.root / "sensevoice.tar.bz2"
            self._download_file(MODEL_ARCHIVE_URL, archive, 0, 94, "下载多语言语音模型…")
            self._set_download(progress=95, message="解压语音模型…")
            self._safe_extract(archive, self.root)
            try:
                archive.unlink()
            except OSError:
                pass
            self._download_file(VAD_URL, self.vad_path, 95, 100, "下载停顿检测模型…")
            self._set_download(state="ready", progress=100, message="语音模型已就绪", error="")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Speech model download failed")
            self._set_download(state="error", message="语音模型下载失败", error=str(exc))

    def _download_file(self, url: str, target: Path, start: int, end: int, message: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        request = Request(url, headers={"User-Agent": "ZCTranslate/voice"})
        with urlopen(request, timeout=60) as response, partial.open("wb") as stream:
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
                received += len(chunk)
                if total:
                    ratio = min(1.0, received / total)
                    progress = start + int((end - start) * ratio)
                    self._set_download(progress=progress, message=message)
        partial.replace(target)

    @staticmethod
    def _safe_extract(archive: Path, destination: Path) -> None:
        destination = destination.resolve()
        with tarfile.open(archive, "r:bz2") as bundle:
            members = []
            for member in bundle.getmembers():
                target = (destination / member.name).resolve()
                if not target.is_relative_to(destination):
                    raise RuntimeError("语音模型压缩包包含非法路径")
                members.append(member)
            bundle.extractall(destination, members=members)

    # --------------------------------------------------------------- sessions
    def start_session(self, mode: str) -> dict[str, Any]:
        if mode not in {"conversation", "input"}:
            raise ValueError("不支持的语音模式")
        status = self.model_status()
        if not status["installed"]:
            raise RuntimeError("请先下载语音识别模型")
        if not status["dependencies"]:
            raise RuntimeError("语音识别依赖未安装，请重新运行环境准备脚本")
        with self._lock:
            if self._session and self._session.state in {"starting", "recording", "processing", "stopping"}:
                raise RuntimeError("已有语音会话正在进行")
            session = SpeechSession(id=uuid.uuid4().hex[:12], mode=mode)
            self._session = session
            session.thread = threading.Thread(
                target=self._run_session, args=(session,), name="speech-session", daemon=True
            )
            session.thread.start()
            return self._session_status_locked(session, 0)

    def stop_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._require_session_locked(session_id)
            if session.state in {"starting", "recording"}:
                session.state = "stopping"
                session.stop_event.set()
            return self._session_status_locked(session, session.next_seq)

    def session_status(self, session_id: str, since: int = 0) -> dict[str, Any]:
        with self._lock:
            session = self._require_session_locked(session_id)
            return self._session_status_locked(session, since)

    def _require_session_locked(self, session_id: str) -> SpeechSession:
        session = self._session
        if not session or session.id != session_id:
            raise KeyError("语音会话不存在")
        return session

    def _session_status_locked(self, session: SpeechSession, since: int) -> dict[str, Any]:
        return {
            "session_id": session.id,
            "mode": session.mode,
            "state": session.state,
            "error": session.error,
            "partial": session.partial,
            "partial_text": session.partial_text,
            "transcript": session.transcript,
            "audio_seconds": round(session.audio_seconds, 1),
            "segments": [item for item in session.segments if int(item["seq"]) > since],
            "next_seq": session.next_seq,
        }

    # ---------------------------------------------------------- recognition run
    def _create_recognizer_and_vad(self):
        recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(self.model_path),
            tokens=str(self.tokens_path),
            num_threads=max(1, min(4, (os.cpu_count() or 2) // 2)),
            use_itn=True,
            debug=False,
        )
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(self.vad_path)
        config.silero_vad.min_silence_duration = PAUSE_SECONDS
        config.silero_vad.min_speech_duration = 0.25
        config.silero_vad.max_speech_duration = MAX_SPEECH_SECONDS
        config.sample_rate = SAMPLE_RATE
        vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=120)
        return recognizer, vad

    @staticmethod
    def _recognize(recognizer: Any, samples: Any) -> tuple[str, str]:
        if len(samples) < int(SAMPLE_RATE * 0.2):
            return "", ""
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        recognizer.decode_stream(stream)
        result = stream.result
        text = str(result.text or "").strip()
        lang = str(result.lang or "").strip().lower().replace("<|", "").replace("|>", "")
        if lang == "jp":
            lang = "ja"
        return text, lang

    def _add_segment(self, session: SpeechSession, text: str, lang: str, duration: float) -> None:
        if not text:
            return
        with self._lock:
            session.next_seq += 1
            session.segments.append({
                "seq": session.next_seq,
                "text": text,
                "lang": lang,
                "timestamp": int((time.time() - session.started_at) * 1000),
                "time": time.strftime("%H:%M:%S"),
                "duration_ms": int(duration * 1000),
            })
            if session.mode == "input":
                session.transcript = "\n".join(
                    str(item.get("text") or "").strip()
                    for item in session.segments
                    if str(item.get("text") or "").strip()
                )
            session.partial = ""
            session.partial_text = ""

    def _run_session(self, session: SpeechSession) -> None:
        try:
            recognizer, vad = self._create_recognizer_and_vad()
            with self._lock:
                session.state = "recording"
            buffer = np.empty(0, dtype=np.float32)
            partial_samples = np.empty(0, dtype=np.float32)
            last_partial_at = 0.0
            window_size = int(vad.config.silero_vad.window_size)
            with sd.InputStream(
                channels=1,
                dtype="float32",
                samplerate=SAMPLE_RATE,
                blocksize=int(SAMPLE_RATE * 0.1),
            ) as stream:
                while not session.stop_event.is_set():
                    samples, _ = stream.read(int(SAMPLE_RATE * 0.1))
                    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
                    session.audio_seconds += len(samples) / SAMPLE_RATE
                    buffer = np.concatenate([buffer, samples])
                    while len(buffer) >= window_size:
                        vad.accept_waveform(buffer[:window_size])
                        buffer = buffer[window_size:]
                    if vad.is_speech_detected():
                        partial_samples = np.concatenate([partial_samples, samples])
                    completed = self._consume_vad(session, recognizer, vad)
                    if completed:
                        partial_samples = np.empty(0, dtype=np.float32)
                    now = time.monotonic()
                    if (
                        len(partial_samples) >= int(SAMPLE_RATE * 0.55)
                        and now - last_partial_at >= 0.75
                    ):
                        preview, _ = self._recognize(recognizer, partial_samples)
                        last_partial_at = now
                        with self._lock:
                            session.partial_text = preview
                    with self._lock:
                        session.partial = "正在听…" if vad.is_speech_detected() else ""
            if len(buffer):
                vad.accept_waveform(buffer)
            vad.flush()
            self._consume_vad(session, recognizer, vad, flush=True)
            if session.mode == "input":
                self._finish_input(session, recognizer)
            else:
                with self._lock:
                    session.state = "done"
                    session.partial = ""
                    session.partial_text = ""
        except Exception as exc:  # noqa: BLE001
            logger.exception("Speech session failed")
            with self._lock:
                session.state = "error"
                session.error = str(exc)
                session.partial = ""
                session.partial_text = ""

    def _consume_vad(self, session: SpeechSession, recognizer: Any, vad: Any, flush: bool = False) -> bool:
        completed = False
        while not vad.empty():
            segment = np.asarray(vad.front.samples, dtype=np.float32).copy()
            vad.pop()
            started = time.perf_counter()
            text, lang = self._recognize(recognizer, segment)
            # Publish completed speech segments in input mode as well, so the
            # client can append each sentence while recording.
            self._add_segment(session, text, lang, time.perf_counter() - started)
            completed = True
        if flush:
            with self._lock:
                session.partial = ""
                session.partial_text = ""
        return completed

    def _finish_input(self, session: SpeechSession, recognizer: Any) -> None:
        with self._lock:
            session.state = "processing"
            pending = list(session.speech_chunks)
            session.speech_chunks.clear()
        for segment in pending:
            text, _ = self._recognize(recognizer, segment)
            if text:
                self._add_segment(session, text, "", 0.0)
        with self._lock:
            session.state = "done"
            session.partial = ""
            session.partial_text = ""
