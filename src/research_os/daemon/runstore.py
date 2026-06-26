"""Run journal — the durable, queryable record of every run.

JUDGE-2 (docs/ROADMAP.md §8): three needs collapse into one primitive.
The RunStore persists each run to ``<root>/.os_state/runs/<run_id>/`` as:

  - ``run.json``  — the manifest: spec + provenance + status transitions +
                    result + artifacts. Written atomically (temp+rename) on
                    every lifecycle transition so a crash never corrupts it.
  - ``log.txt``   — the full captured stdout/stderr (the bounded tail in
                    run.json is for quick reads; this is the complete log).

This makes jobs survive a daemon restart (durability), makes every run
reproducible (provenance), and gives the gateway/dashboard a permanent,
queryable history (observability) — all from one file format.

stdlib only (json, os, time, pathlib, tempfile). No locking beyond atomic
rename: each run owns its own directory, so concurrent runs never touch
the same files.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RUNS_DIRNAME = "runs"
MANIFEST_NAME = "run.json"
LOG_NAME = "log.txt"


class RunStore:
    """Read/write the durable run journal under a project root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @property
    def runs_dir(self) -> Path:
        return self.root / ".os_state" / RUNS_DIRNAME

    def _run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    # ── writing ────────────────────────────────────────────────────────
    def write_manifest(self, run_id: str, manifest: dict) -> Path:
        """Atomically write a run's manifest. Creates the run dir if needed."""
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / MANIFEST_NAME
        # Atomic: write to a temp file in the same dir, then rename.
        fd, tmp = tempfile.mkstemp(dir=str(run_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2, default=str)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        return target

    def append_log(self, run_id: str, line: str) -> None:
        """Append one line to a run's full log. Best-effort, never raises."""
        run_dir = self._run_dir(run_id)
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            with (run_dir / LOG_NAME).open("a", encoding="utf-8") as fh:
                fh.write(line.rstrip("\n") + "\n")
        except OSError:
            pass

    # ── reading ────────────────────────────────────────────────────────
    def read_manifest(self, run_id: str) -> dict | None:
        """Read one run's manifest, or None if missing/corrupt."""
        target = self._run_dir(run_id) / MANIFEST_NAME
        if not target.exists():
            return None
        try:
            with target.open(encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def read_log(self, run_id: str, *, tail: int | None = None) -> list[str]:
        """Read a run's full log (or the last ``tail`` lines)."""
        target = self._run_dir(run_id) / LOG_NAME
        if not target.exists():
            return []
        try:
            with target.open(encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return []
        if tail is not None and tail >= 0:
            return lines[-tail:]
        return lines

    def list_runs(self, *, limit: int = 50) -> list[dict]:
        """List run manifests, newest first (by submitted_at, then dir mtime).

        Returns lightweight summaries (no full provenance/result) so a list
        call stays cheap even with thousands of runs.
        """
        if not self.runs_dir.exists():
            return []
        entries: list[tuple[float, dict]] = []
        for child in self.runs_dir.iterdir():
            if not child.is_dir():
                continue
            # Per-record fault isolation: a single malformed manifest must NOT
            # sink the whole list (which would silently abandon every orphan in
            # detect_orphans). Skip the bad one, keep the rest.
            try:
                manifest = self.read_manifest(child.name)
                if manifest is None:
                    continue
                sort_key = manifest.get("submitted_at")
                if not isinstance(sort_key, (int, float)):
                    try:
                        sort_key = child.stat().st_mtime
                    except OSError:
                        sort_key = 0.0
                entries.append((float(sort_key), self._summarize(manifest)))
            except Exception:  # noqa: BLE001 - one bad record can't break recovery
                logger.warning("skipping unreadable run manifest %s", child.name, exc_info=True)
                continue
        entries.sort(key=lambda e: e[0], reverse=True)
        return [summary for _key, summary in entries[:limit]]

    @staticmethod
    def _summarize(manifest: dict) -> dict:
        """Lightweight view for list endpoints. Type-defensive: a manifest whose
        `result` isn't a dict or `artifacts` isn't a list must not raise (a bad
        record would otherwise sink list_runs → detect_orphans → all recovery)."""
        result = manifest.get("result")
        result = result if isinstance(result, dict) else {}
        artifacts = manifest.get("artifacts")
        artifacts = artifacts if isinstance(artifacts, list) else []
        return {
            "id": manifest.get("id"),
            "name": manifest.get("name"),
            "kind": manifest.get("kind"),
            "status": manifest.get("status"),
            "submitted_at": manifest.get("submitted_at"),
            "started_at": manifest.get("started_at"),
            "finished_at": manifest.get("finished_at"),
            "duration_s": manifest.get("duration_s"),
            "root": manifest.get("root"),
            "returncode": result.get("returncode"),
            "artifact_count": len(artifacts),
        }

    # ── rehydration ────────────────────────────────────────────────────
    def recent_manifests(self, *, limit: int = 100) -> list[dict]:
        """Full manifests for the most recent runs (for restart rehydration)."""
        summaries = self.list_runs(limit=limit)
        out: list[dict] = []
        for s in summaries:
            rid = s.get("id")
            if not rid:
                continue
            full = self.read_manifest(rid)
            if full is not None:
                out.append(full)
        return out

    def detect_orphans(self) -> list[str]:
        """Run ids whose last persisted status was non-terminal AND not paused.

        After an unclean shutdown these runs were RUNNING/QUEUED but the
        process died — they can never resume, so the daemon should mark them
        INTERRUPTED on startup rather than leave them looking live forever.

        ``paused`` is deliberately treated as terminal-for-recovery: a paused
        run is a USER INTENT, not a crash artifact, so it must NOT be rewritten
        to ``interrupted`` on restart (that would lose the pause and make the
        watchdog nag to resume a run the researcher intentionally held).
        """
        orphans: list[str] = []
        terminal = {"succeeded", "failed", "cancelled", "interrupted", "paused"}
        for s in self.list_runs(limit=10_000):
            status = (s.get("status") or "").lower()
            if status and status not in terminal:
                rid = s.get("id")
                if rid:
                    orphans.append(rid)
        return orphans

    def mark_interrupted(self, run_id: str) -> None:
        """Rewrite an orphaned run's manifest as INTERRUPTED. Best-effort."""
        manifest = self.read_manifest(run_id)
        if manifest is None:
            return
        manifest["status"] = "interrupted"
        manifest.setdefault("finished_at", time.time())
        transitions = manifest.setdefault("transitions", [])
        transitions.append({"status": "interrupted", "at": time.time(),
                             "note": "daemon restarted while run was active"})
        try:
            self.write_manifest(run_id, manifest)
        except OSError:
            pass


def build_manifest(
    *,
    run_id: str,
    name: str,
    kind: str,
    status: str,
    root: str | None,
    spec: dict | None = None,
    provenance: dict | None = None,
    submitted_at: float | None = None,
    **extra: Any,
) -> dict:
    """Construct a fresh run manifest with the standard fields."""
    manifest: dict = {
        "id": run_id,
        "name": name,
        "kind": kind,
        "status": status,
        "root": root,
        "submitted_at": submitted_at if submitted_at is not None else time.time(),
        "spec": spec or {},
        "provenance": provenance or {},
        "transitions": [{"status": status, "at": time.time()}],
        "artifacts": [],
    }
    manifest.update(extra)
    return manifest


class RunJournal:
    """Drives a RunStore from the event bus — the strangler-fig bridge.

    The task queue already emits ``job.{submitted,started,succeeded,failed,
    cancelled}`` (each carrying a full job snapshot) and ``job.log`` line
    events. RunJournal subscribes to those and persists them to the durable
    store, so the queue needs zero knowledge of the journal. Wiring is a
    single ``daemon.bus.subscribe`` consumed on a background thread.

    Each run is keyed by job id. The first event for a job writes the
    manifest (with provenance from the job spec); subsequent transitions
    rewrite it; ``job.log`` lines append to the full log file and grow the
    bounded ``log_tail``.
    """

    LOG_TAIL_MAX = 200

    def __init__(self, store: RunStore) -> None:
        self.store = store
        self._tails: dict[str, list[str]] = {}
        # Optional callback the daemon sets to react to a run reaching a
        # terminal state (e.g. autonomous continuation). Signature:
        # on_terminal(manifest: dict) -> None. Best-effort, never blocks the
        # journal — kept out of RunJournal so the journal stays config-free.
        self.on_terminal: Any = None

    def handle(self, event: Any) -> None:
        """Process one event object (must have .kind and .data). Never raises."""
        try:
            kind = getattr(event, "kind", None)
            data = getattr(event, "data", None) or {}
            if kind == "job.log":
                self._on_log(data)
            elif kind == "job.pid":
                self._on_pid(data)
            elif isinstance(kind, str) and kind.startswith("job."):
                self._on_transition(kind, data)
        except Exception:  # noqa: BLE001 - journal must never break the bus
            pass

    def _on_pid(self, data: dict) -> None:
        """Persist the child PID (+ host) so crash-recovery can check liveness."""
        job_id = data.get("job_id") or data.get("id")
        pid = data.get("pid")
        if not job_id or pid is None:
            return
        manifest = self.store.read_manifest(job_id)
        if manifest is None:
            return
        import socket
        manifest["pid"] = pid
        manifest["host"] = socket.gethostname()
        try:
            self.store.write_manifest(job_id, manifest)
        except OSError:
            pass

    def _on_log(self, data: dict) -> None:
        job_id = data.get("job_id") or data.get("id")
        line = data.get("line")
        if not job_id or line is None:
            return
        self.store.append_log(job_id, str(line))
        tail = self._tails.setdefault(job_id, [])
        tail.append(str(line))
        if len(tail) > self.LOG_TAIL_MAX:
            del tail[: len(tail) - self.LOG_TAIL_MAX]

    def _on_transition(self, kind: str, data: dict) -> None:
        snap = data.get("job") or {}
        job_id = data.get("job_id") or snap.get("id")
        if not job_id:
            return
        status = (snap.get("status") or data.get("status") or "").lower()
        existing = self.store.read_manifest(job_id)
        # Terminal-once idempotency guard: if this run is ALREADY terminal, a
        # second terminal event (bus replay / duplicate emit) must be a no-op —
        # otherwise it double-appends a transition and double-fires on_terminal
        # (which double-advances autonomous continuation, spending compute/tokens
        # twice). Non-terminal → terminal still proceeds normally.
        _TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
        if existing is not None:
            prev = (existing.get("status") or "").lower()
            if prev in _TERMINAL and status in _TERMINAL:
                return
        if existing is None:
            manifest = build_manifest(
                run_id=job_id,
                name=snap.get("name", "run"),
                kind=snap.get("kind", "callable"),
                status=status or "queued",
                root=snap.get("root"),
                spec=snap.get("spec") or {},
                provenance=snap.get("provenance") or {},
                submitted_at=snap.get("submitted_at"),
            )
        else:
            manifest = existing
            manifest["status"] = status or manifest.get("status")
            manifest.setdefault("transitions", []).append(
                {"status": status, "at": time.time()}
            )
        # Timing + result mirror the snapshot.
        for fld in ("started_at", "finished_at", "duration_s", "error"):
            if snap.get(fld) is not None:
                manifest[fld] = snap[fld]
        if snap.get("result") is not None:
            manifest["result"] = snap["result"]
        result = snap.get("result")
        # Hoist output artifacts to the top level so list summaries and the
        # provenance record surface them without digging into result.
        if isinstance(result, dict) and result.get("artifacts"):
            manifest["artifacts"] = result["artifacts"]
            if result.get("artifacts_truncated"):
                manifest["artifacts_truncated"] = True
        # Reconcile command success with run success: a subprocess job that
        # *ran* (job status "succeeded") but whose command exited nonzero is a
        # FAILED run from the researcher's point of view. Cancelled runs keep
        # their cancelled status.
        if (
            status == "succeeded"
            and isinstance(result, dict)
            and result.get("returncode") not in (None, 0)
        ):
            if result.get("cancelled"):
                manifest["status"] = "cancelled"
            else:
                manifest["status"] = "failed"
            status = manifest["status"]
        tail = self._tails.get(job_id)
        if tail:
            manifest["log_tail"] = list(tail)
        self.store.write_manifest(job_id, manifest)
        # Free the in-memory tail once the run is terminal.
        if status in {"succeeded", "failed", "cancelled"}:
            self._tails.pop(job_id, None)
            # Auto-refresh the staleness verdict the reasoning-side gate reads.
            # Without this the verdict was written ONLY by an authenticated
            # POST /v1/staleness/verdict, so the no_stale_inputs floor gate
            # never fired in normal use. Recompute from the just-updated
            # journal + persist the sidecar. Best-effort: a failure here never
            # touches the run record (matches the bus-isolation contract).
            self._refresh_staleness_verdict()
            # Fire the optional terminal hook (autonomous continuation, etc.).
            # Best-effort + isolated: a hook failure never touches the run
            # record or the bus.
            if self.on_terminal is not None:
                try:
                    self.on_terminal(manifest)
                except Exception:  # noqa: BLE001 - hook must not break the journal
                    pass

    def _refresh_staleness_verdict(self) -> None:
        """Recompute + persist the freshness verdict from the run journal.

        Runs after every terminal run so the on-disk verdict the staleness
        floor gate reads (.os_state/staleness/verdict.json) stays current
        without requiring an explicit authenticated call. Pure best-effort.
        """
        try:
            from . import provenance as _prov
            from . import staleness as _stale

            root = getattr(self.store, "root", None)
            if root is None:
                return
            manifests = self.store.recent_manifests(limit=200)
            if not manifests:
                return
            hash_file = _prov.hash_fn_for_root(root)
            report = _stale.assess(manifests, hash_file)
            _stale.write_verdict(root, report)
        except Exception:  # noqa: BLE001 - verdict refresh must never break the journal
            logger.debug("staleness verdict refresh failed", exc_info=True)
