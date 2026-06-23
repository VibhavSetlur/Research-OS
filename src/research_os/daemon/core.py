"""Daemon core — the holder object and status report (Phase 0 skeleton).

The :class:`Daemon` is, for now, a thin holder: it resolves the project
root using the SAME resolver the stdio MCP server uses, carries a
:class:`DaemonConfig`, and can produce a :class:`DaemonStatus` snapshot
by reading the existing :class:`ResearchLedger` and active plan.

It does NOT serve anything yet. Phase 1 adds the persistent core loop and
the read-only HTTP state endpoints; Phase 2 adds the gateway; etc. Each
of those bolts onto this object without changing its construction
contract.

Everything here reuses existing engine functions — no routing, state, or
protocol logic is re-implemented (strangler-fig; see docs/v4/ROADMAP.md).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import DaemonConfig
from .events import EventBus
from .registry import WorkspaceRegistry
from .runstore import RunStore
from .tasks import TaskQueue

logger = logging.getLogger("research-os.daemon")


@dataclass
class DaemonStatus:
    """A point-in-time, read-only snapshot of daemon + project state.

    Serializable to a plain dict for the future ``/v1/state`` endpoint and
    the ``research-os daemon status`` CLI.
    """

    serving: bool
    version: str
    config: dict
    root: str | None
    project_initialized: bool
    active_protocol: str | None = None
    progress: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    roots: list = field(default_factory=list)
    jobs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "serving": self.serving,
            "version": self.version,
            "config": self.config,
            "root": self.root,
            "project_initialized": self.project_initialized,
            "active_protocol": self.active_protocol,
            "progress": self.progress,
            "notes": self.notes,
            "roots": self.roots,
            "jobs": self.jobs,
        }


class Daemon:
    """The Research OS gateway daemon (Phase 0 skeleton).

    Construct with an explicit root + config, or use :meth:`for_root` /
    :meth:`autoresolve` to build one the way the MCP server resolves its
    workspace.
    """

    def __init__(self, root: Path | None, config: DaemonConfig) -> None:
        self.root = root
        self.config = config
        # Set True by serve() once the process is actually listening.
        self._serving = False
        # Event spine (Phase 1.5): append-only bus the task queue, gateway,
        # dashboard, and MCP sidecar all publish to / subscribe from. This is
        # the substrate that makes the daemon observable in real time instead
        # of poll-only. stdlib-only, import-cheap.
        self.events = EventBus()
        # Multi-root state registry + background task queue (Phase 1).
        # Both are stdlib-only and import-cheap; constructing them here keeps
        # status() and serve() working off the same engine seams. The queue
        # publishes job lifecycle events to the bus.
        self.registry = WorkspaceRegistry(cache_ttl=config.state_cache_ttl)
        self.tasks = TaskQueue(max_workers=config.task_workers, bus=self.events)
        # Durable run journal (Phase 1.7): persists every run to
        # <root>/.os_state/runs/ as a provenance manifest + full log, driven
        # off the event bus so the queue stays journal-agnostic. Only active
        # when we have a concrete root to write under.
        self.runstore = RunStore(root) if root is not None else None
        self._journal = None
        self._journal_thread = None
        if root is not None:
            self.registry.register(root)

    # ── construction helpers ──────────────────────────────────────────
    @classmethod
    def autoresolve(cls, **overrides: object) -> "Daemon":
        """Build a daemon for the auto-resolved project root.

        Reuses the server's resolver (``RESEARCH_OS_WORKSPACE`` env ->
        nearest ``.os_state`` -> cwd) so the daemon and the MCP server
        always agree on which project is active.
        """
        root = _resolve_root()
        return cls.for_root(root, **overrides)

    @classmethod
    def for_root(cls, root: Path | str | None, **overrides: object) -> "Daemon":
        # Normalize to Path early so config resolution, status(), and the
        # registry all get a real Path (callers may pass a str).
        if root is not None and not isinstance(root, Path):
            root = Path(root)
        config = DaemonConfig.resolve(root=root, **overrides)
        return cls(root=root, config=config)

    # ── introspection ─────────────────────────────────────────────────
    @property
    def serving(self) -> bool:
        return self._serving

    def status(self) -> DaemonStatus:
        """Produce a read-only status snapshot from existing engine state.

        Never raises: any read failure is captured as a note so the status
        endpoint/CLI stays robust even on a half-initialized project.
        """
        from research_os import __version__

        notes: list = []
        root = self.root
        initialized = bool(root and (root / ".os_state").exists())
        active_protocol: str | None = None
        progress: dict = {}

        if initialized and root is not None:
            active_protocol = _safe_active_protocol(root, notes)
            progress = _safe_progress(root, notes)
        elif root is None:
            notes.append("no project root resolved")
        else:
            notes.append("root has no .os_state (run 'research-os init')")

        return DaemonStatus(
            serving=self._serving,
            version=__version__,
            config={
                "host": self.config.host,
                "port": self.config.port,
                "base_url": self.config.base_url,
                "enable_gateway": self.config.enable_gateway,
                "enable_dashboard": self.config.enable_dashboard,
                "sandbox_mode": self.config.sandbox_mode,
                "task_workers": self.config.task_workers,
                "state_cache_ttl": self.config.state_cache_ttl,
            },
            root=str(root) if root else None,
            project_initialized=initialized,
            active_protocol=active_protocol,
            progress=progress,
            notes=notes,
            roots=self.registry.roots(),
            jobs=self.tasks.snapshot(limit=10),
        )

    # ── execution ─────────────────────────────────────────────────────
    def run_command(
        self,
        cmd: "str | list[str]",
        *,
        name: str | None = None,
        cwd: str | None = None,
        env: dict | None = None,
        root: str | None = None,
        shell: bool = False,
        inputs: "list[str] | None" = None,
        track_packages: "list[str] | None" = None,
        track_artifacts: bool = True,
    ) -> str:
        """Submit an external command as a background job and return its id.

        This is the "any language" entry point: anything with a CLI
        (Rscript, julia, bash, snakemake, nextflow, sbatch, …) runs through
        the SubprocessRunner, streaming output as ``job.log`` events on the
        bus and recording a bounded result handle. Defaults ``cwd`` to the
        daemon's root so commands run in the project by default.

        Provenance (git commit, environment, input hashes) is captured at
        submit time and recorded on the job so the durable run journal can
        make the run reproducible. Capture is best-effort and never blocks.
        """
        from . import provenance as _prov
        from .runners import SubprocessRunner

        effective_cwd = cwd or (str(self.root) if self.root else None)
        effective_root = root or (str(self.root) if self.root else None)
        runner = SubprocessRunner(
            cmd,
            cwd=effective_cwd,
            env=env,
            shell=shell,
            track_artifacts=track_artifacts,
        )
        job_name = name or (cmd if isinstance(cmd, str) else " ".join(cmd))
        prov = _prov.capture(
            effective_root or effective_cwd or ".",
            inputs=inputs,
            packages=track_packages,
        )
        spec = {
            "cmd": cmd,
            "cwd": effective_cwd,
            "shell": shell,
            "env_overrides": sorted(env.keys()) if env else [],
        }
        # Ensure the durable journal is capturing before we submit, so even
        # programmatic use (no serve()) gets a persistent record.
        self._start_journal()
        return self.tasks.submit(
            runner,
            name=job_name[:120],
            root=effective_root,
            kind="subprocess",
            spec=spec,
            provenance=prov,
        )

    # ── run journal (durable, Phase 1.7) ──────────────────────────────
    def _start_journal(self) -> None:
        """Begin persisting runs to the durable journal off the event bus.

        Idempotent. Also rehydrates: any run whose last persisted status was
        non-terminal (the daemon died mid-run) is marked INTERRUPTED so the
        history reflects reality instead of showing a phantom live run.
        """
        if self.runstore is None or self._journal is not None:
            return
        import threading as _threading

        from .runstore import RunJournal

        # Rehydrate: mark orphaned (non-terminal) runs from a prior crash.
        try:
            for rid in self.runstore.detect_orphans():
                self.runstore.mark_interrupted(rid)
        except Exception:  # noqa: BLE001 - rehydration must not block startup
            logger.debug("run journal rehydration failed", exc_info=True)

        journal = RunJournal(self.runstore)
        self._journal = journal

        def _pump() -> None:
            # Backfill any events already on the bus (defensive — the journal
            # starts before HTTP accepts requests, but a programmatic submit
            # could race), then stream live. Skip heartbeat sentinels.
            for event in self.events.subscribe(backfill=1000):
                if getattr(event, "kind", None) == "heartbeat":
                    continue
                journal.handle(event)

        thread = _threading.Thread(
            target=_pump, name="ro-daemon-journal", daemon=True
        )
        self._journal_thread = thread
        thread.start()
        logger.debug("run journal started under %s", self.runstore.runs_dir)

    # ── lifecycle ─────────────────────────────────────────────────────
    def serve(self) -> None:
        """Start the persistent daemon: task queue + read-only HTTP server.

        Blocks until interrupted. The HTTP layer (starlette/uvicorn) is in
        the optional ``[daemon]`` extra and imported lazily; if it's absent
        this raises a clear "install research-os[daemon]" error rather than
        a bare ImportError.

        The stdio MCP server is untouched — this is a separate, additive,
        opt-in surface (strangler-fig).
        """
        from . import server as _server

        # Fail fast with the actionable hint BEFORE we start the queue, so a
        # missing extra doesn't leave a worker pool dangling.
        _server._require_web_stack()
        self.tasks.start()
        self._start_journal()
        self._serving = True
        try:
            _server.serve(self)
        finally:
            self._serving = False
            self.tasks.shutdown(wait=False)


# ── private helpers: reuse the existing engine, never reimplement ──────
def _resolve_root() -> Path | None:
    """Resolve the active project root the same way the MCP server does."""
    try:
        from research_os.server.entry import _resolve_project_root
        return _resolve_project_root()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("root resolution failed: %s", exc)
        return None


def _safe_active_protocol(root: Path, notes: list) -> str | None:
    """Read the active plan's protocol via the existing router helper."""
    try:
        from research_os.tools.actions.router import _load_active_plan
        plan = _load_active_plan(root) or {}
        proto = plan.get("protocol") or plan.get("protocol_name")
        return str(proto) if proto else None
    except Exception as exc:
        notes.append(f"active-plan read skipped: {type(exc).__name__}")
        return None


def _safe_progress(root: Path, notes: list) -> dict:
    """Read a compact progress digest via existing engine state.

    Tries the planning progress digest first; falls back to a minimal
    ledger summary. Always returns a dict.
    """
    try:
        from research_os.tools.actions.research.planning import progress_digest
        digest = progress_digest(root)
        if isinstance(digest, dict):
            return digest
    except Exception as exc:
        notes.append(f"progress digest skipped: {type(exc).__name__}")
    return {}
