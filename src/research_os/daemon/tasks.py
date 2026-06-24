"""Background task queue — the daemon's "master loop owns execution" primitive.

The v4 thesis is that Research OS should be able to own long-running work
(batch-fetching papers, multi-hour simulations, pipeline DAGs) independently
of whichever chat client happens to be connected. This module is the
foundation of that: an in-process queue that runs submitted jobs on a pool
of worker threads, off the request thread, and exposes their status as a
read-only snapshot.

Phase 1 scope (deliberately small + correct):
  - submit(fn, *args, name=, root=, **kwargs) -> job_id
  - jobs run on a bounded worker pool, FIFO
  - each job carries status (queued -> running -> succeeded/failed/cancelled),
    timing, result/error, and the resolving project root
  - snapshot() returns a JSON-serializable view for /v1/jobs and the CLI
  - graceful shutdown drains/stops workers

Design decisions (see docs/v4/ROADMAP.md §6):
  - In-memory for Phase 1. Persistence across daemon restarts is an OPEN
    decision flagged for a judge phase — the JobStore boundary here is
    deliberately narrow so a persistent backend can slot in later without
    touching callers.
  - stdlib only (threading, queue, uuid, dataclasses). No new deps; this
    must import in core installs without the [daemon] extra.
  - Jobs call EXISTING engine functions (strangler-fig). The queue knows
    nothing about research; it only schedules callables.

Cancellation is cooperative: a job that has not started yet is cancelled
outright; a running job cannot be force-killed (Python threads can't be),
so we set a flag the job *may* observe via its `cancel_event`.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("research-os.daemon.tasks")


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass
class Job:
    """A unit of background work and its lifecycle state.

    The ``cancel_event`` is passed to cooperative jobs that accept a
    ``cancel_event`` keyword; long-running engine work can poll it to bail
    out early. Jobs that don't accept it simply run to completion.
    """

    id: str
    name: str
    status: JobStatus = JobStatus.QUEUED
    root: str | None = None
    submitted_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    # Provenance metadata (Phase 1.7) — populated for runs that want a durable
    # journal entry. The queue treats these as opaque; the run journal reads
    # them. ``kind`` distinguishes python-callable from subprocess/scheduler.
    kind: str = "callable"
    spec: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-serializable view. Result is included only if it's trivially
        serializable; otherwise its type name is reported (the queue must
        never raise inside a status read)."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "root": self.root,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": (
                round(self.finished_at - self.started_at, 3)
                if self.started_at and self.finished_at
                else None
            ),
            "result": _jsonsafe(self.result),
            "error": self.error,
            "kind": self.kind,
            "spec": _jsonsafe(self.spec),
            "provenance": _jsonsafe(self.provenance),
        }


def _jsonsafe(value: Any) -> Any:
    """Best-effort: keep JSON primitives/containers, else stringify the type."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonsafe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonsafe(v) for k, v in value.items()}
    return f"<{type(value).__name__}>"


class TaskQueue:
    """A small, thread-safe background job queue.

    Not a general scheduler — just enough to take long work off the request
    thread and report on it. Bounded worker pool; FIFO dispatch.
    """

    def __init__(
        self,
        max_workers: int = 2,
        max_history: int = 200,
        bus: Any = None,
        notify_command: str = "",
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self._max_workers = max_workers
        self._max_history = max_history
        self._bus = bus  # optional EventBus for lifecycle events
        # Researcher-notification delivery command (notification spine).
        # When set, terminal job events also push a notification so the
        # researcher learns a long job finished without polling.
        self._notify_command = notify_command or ""
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._pending: queue.Queue[str] = queue.Queue()
        self._executor: ThreadPoolExecutor | None = None
        self._started = False
        self._closed = False

    # ── lifecycle ────────────────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="ro-daemon-job",
            )
            self._started = True
            self._closed = False
            logger.debug("task queue started (max_workers=%d)", self._max_workers)

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
            executor = self._executor
            self._executor = None
            self._started = False
        if executor is not None:
            executor.shutdown(wait=wait)
            logger.debug("task queue shut down (wait=%s)", wait)

    # ── events ───────────────────────────────────────────────────────
    def _emit(self, kind: str, job: Job) -> None:
        """Publish a job lifecycle event if a bus is wired. Never raises."""
        # Terminal events also feed the notification spine so the researcher
        # learns a long job finished without polling (intent #4). Best-effort
        # and fully isolated: a notification failure never affects the job or
        # the event publish.
        if kind in ("job.succeeded", "job.failed", "job.cancelled") and job.root:
            try:
                from . import notifications as _ntfy

                _ntfy.emit_job_terminal(
                    job.root, job.to_dict(), notify_command=self._notify_command
                )
            except Exception:  # noqa: BLE001 - notify must never break a job
                logger.debug("job notification failed for %s", kind, exc_info=True)
        if self._bus is None:
            return
        try:
            self._bus.publish(
                kind,
                data={
                    "job_id": job.id,
                    "name": job.name,
                    "status": job.status.value,
                    # Full snapshot so durable consumers (run journal) have
                    # everything they need without re-querying the queue.
                    "job": job.to_dict(),
                },
                root=job.root,
            )
        except Exception:  # noqa: BLE001 - telemetry must never break a job
            logger.debug("event publish failed for %s", kind, exc_info=True)

    # ── submission ───────────────────────────────────────────────────
    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        name: str | None = None,
        root: str | None = None,
        kind: str = "callable",
        spec: dict | None = None,
        provenance: dict | None = None,
        **kwargs: Any,
    ) -> str:
        """Schedule ``fn(*args, **kwargs)`` to run on a worker thread.

        Returns the job id immediately. If ``fn`` accepts a ``cancel_event``
        keyword, the job's event is injected so the work can cooperatively
        bail when cancelled.

        ``kind``/``spec``/``provenance`` are opaque metadata recorded on the
        job for the durable run journal (Phase 1.7); the queue does not
        interpret them.
        """
        with self._lock:
            if not self._started or self._executor is None:
                raise RuntimeError("TaskQueue.submit() before start()")
            if self._closed:
                raise RuntimeError("TaskQueue is closed")
            job = Job(
                id=uuid.uuid4().hex[:12],
                name=name or getattr(fn, "__name__", "job"),
                root=root,
                kind=kind,
                spec=spec or {},
                provenance=provenance or {},
            )
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._evict_history_locked()
            executor = self._executor

        executor.submit(self._run, job, fn, args, kwargs)
        self._emit("job.submitted", job)
        logger.debug("submitted job %s (%s)", job.id, job.name)
        return job.id

    def _run(self, job: Job, fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        # Honor a cancel that landed while the job was still queued.
        if job.cancel_event.is_set():
            with self._lock:
                job.status = JobStatus.CANCELLED
                job.finished_at = time.time()
            self._emit("job.cancelled", job)
            return
        with self._lock:
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
        self._emit("job.started", job)
        # Inject cancel_event only if the callable wants it.
        call_kwargs = dict(kwargs)
        try:
            import inspect

            params = inspect.signature(fn).parameters
            if "cancel_event" in params:
                call_kwargs["cancel_event"] = job.cancel_event
            # If the callable can stream progress, give it an emit() bound to
            # this job's context so its log lines land on the bus tagged with
            # the job id + root (the foundation for live log tailing).
            if "emit" in params and self._bus is not None:
                def _emit_for_job(kind: str, data: dict, _job=job) -> None:
                    payload = {"job_id": _job.id, "name": _job.name, **data}
                    self._bus.publish(kind, data=payload, root=_job.root)

                call_kwargs["emit"] = _emit_for_job
        except (TypeError, ValueError):
            pass
        try:
            result = fn(*args, **call_kwargs)
            with self._lock:
                if job.cancel_event.is_set():
                    job.status = JobStatus.CANCELLED
                else:
                    job.status = JobStatus.SUCCEEDED
                    job.result = result
        except Exception as exc:  # noqa: BLE001 - record any failure
            logger.warning("job %s failed: %s", job.id, exc)
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = f"{type(exc).__name__}: {exc}"
                job._traceback = traceback.format_exc()  # type: ignore[attr-defined]
        finally:
            with self._lock:
                job.finished_at = time.time()
                # The job is now terminal — run an eviction pass so completed
                # work doesn't accumulate past max_history (submit-time
                # eviction can't reclaim jobs that were still queued then).
                self._evict_history_locked()
                terminal_status = job.status
            self._emit(f"job.{terminal_status.value}", job)

    # ── cancellation ─────────────────────────────────────────────────
    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns True if the job exists and was not
        already terminal. Queued jobs are cancelled outright; running jobs
        get a cooperative signal (no force-kill — threads can't be killed)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status.terminal:
                return False
            job.cancel_event.set()
            cancelled_now = False
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                job.finished_at = time.time()
                cancelled_now = True
        if cancelled_now:
            self._emit("job.cancelled", job)
        return True

    # ── introspection ────────────────────────────────────────────────
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self, root: str | None = None, limit: int | None = None) -> dict:
        """Read-only view for /v1/jobs and the CLI. Newest first.

        ``root`` filters to a single project; ``limit`` caps the count.
        """
        with self._lock:
            ids = list(reversed(self._order))
            jobs = [self._jobs[i] for i in ids if i in self._jobs]
        if root is not None:
            jobs = [j for j in jobs if j.root == root]
        if limit is not None:
            jobs = jobs[:limit]
        counts: dict[str, int] = {}
        with self._lock:
            for j in self._jobs.values():
                counts[j.status.value] = counts.get(j.status.value, 0) + 1
        return {
            "jobs": [j.to_dict() for j in jobs],
            "counts": counts,
            "total": len(self._jobs),
            "max_workers": self._max_workers,
        }

    # ── internal ─────────────────────────────────────────────────────
    def _evict_history_locked(self) -> None:
        """Drop oldest TERMINAL jobs once history exceeds the cap. Never
        evicts a queued/running job (its worker still holds a reference)."""
        if len(self._order) <= self._max_history:
            return
        keep: list[str] = []
        removable = [
            jid for jid in self._order
            if (j := self._jobs.get(jid)) is not None and j.status.terminal
        ]
        to_remove = len(self._order) - self._max_history
        remove_set = set(removable[:to_remove])
        for jid in self._order:
            if jid in remove_set:
                self._jobs.pop(jid, None)
            else:
                keep.append(jid)
        self._order = keep
