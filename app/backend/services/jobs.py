"""A small single-worker job queue used for translations and benchmarks.

OpenVINO inference is blocking and the NPU/GPU pipeline is serialized, so one
worker is the correct concurrency model.  Jobs publish events to an asyncio
queue owned by the HTTP request that submitted them.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class QueueFull(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    kind: str
    loop: asyncio.AbstractEventLoop
    events: asyncio.Queue
    fn: Callable[..., None] | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    created_at: float = field(default_factory=time.time)
    state: str = "queued"
    error: str = ""

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        payload = {"event": event, "data": data or {}}
        try:
            self.loop.call_soon_threadsafe(self.events.put_nowait, payload)
        except RuntimeError:
            # The event loop is closed (window closed); stop generation.
            self.cancel.set()


JobFn = Callable[[Callable[[str, dict[str, Any] | None], None], threading.Event], None]


class JobQueue:
    def __init__(self, max_pending: int = 3) -> None:
        self.max_pending = max_pending
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._active: Job | None = None
        self._worker = threading.Thread(target=self._run, name="inference-worker", daemon=True)
        self._stopped = False

    def start(self) -> None:
        if not self._worker.is_alive():
            self._worker.start()

    def submit(self, kind: str, fn: JobFn, loop: asyncio.AbstractEventLoop) -> Job:
        with self._lock:
            pending = len(self._jobs)
            if pending >= self.max_pending:
                raise QueueFull("当前有翻译任务在进行，请稍后再试。")
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, loop=loop,
                      events=asyncio.Queue(), fn=fn)
            self._jobs[job.id] = job
        self._queue.put(job)
        return job

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return False
        job.cancel.set()
        return True

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def counts(self) -> dict[str, int]:
        with self._lock:
            active = 1 if self._active else 0
            return {"active": active, "pending": max(0, len(self._jobs) - active)}

    def shutdown(self) -> None:
        self._stopped = True
        self._queue.put(None)

    def _run(self) -> None:
        while not self._stopped:
            job = self._queue.get()
            if job is None:
                break
            with self._lock:
                self._active = job
                job.state = "running"
            try:
                if job.fn is None:
                    raise RuntimeError("job has no function")
                job.fn(job.emit, job.cancel)
                job.state = "done"
            except Exception as exc:  # noqa: BLE001
                job.state = "error"
                job.error = str(exc)
                traceback.print_exc()
                job.emit("error", {"code": "INTERNAL", "message": str(exc)})
            finally:
                with self._lock:
                    self._active = None
                    # Remove finished jobs after consumers have had a chance to
                    # read the terminal event.  Cancel is a no-op afterwards.
                    self._jobs.pop(job.id, None)

def submit_job(job_queue: JobQueue, kind: str, fn: JobFn,
               loop: asyncio.AbstractEventLoop) -> Job:
    return job_queue.submit(kind, fn, loop)
