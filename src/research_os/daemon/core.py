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
        # Set True by Phase 1's core loop once the process is actually
        # listening. Phase 0 never serves.
        self._serving = False

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
    def for_root(cls, root: Path | None, **overrides: object) -> "Daemon":
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
            },
            root=str(root) if root else None,
            project_initialized=initialized,
            active_protocol=active_protocol,
            progress=progress,
            notes=notes,
        )

    # ── lifecycle (filled in by later phases) ─────────────────────────
    def serve(self) -> None:
        """Start serving. Not implemented in the Phase 0 skeleton.

        Phase 1 implements the persistent core loop + read-only HTTP
        endpoints here. Until then this raises a clear, actionable error
        rather than silently doing nothing.
        """
        raise NotImplementedError(
            "The Research OS daemon serving loop is not implemented yet "
            "(Phase 1). Phase 0 ships the skeleton + 'research-os daemon "
            "status'. Track progress in docs/v4/ROADMAP.md."
        )


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
