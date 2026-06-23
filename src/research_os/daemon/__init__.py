"""Research OS daemon — the multi-protocol gateway (skeleton).

This package is the v4 architecture's home: a persistent, headless,
localhost daemon that owns the master execution state machine and exposes
Research OS to any client (IDE, web UI, CLI, MCP sidecar) at once.

DESIGN STANCE (read docs/v4/ROADMAP.md before extending this):

* Strangler-fig. The daemon WRAPS the existing engine functions
  (``router.route_request``, ``ResearchLedger``, ``dispatch._handle_tool_call``)
  — it never re-implements routing, state, or protocol logic.
* Additive + opt-in. The stdio MCP server (``research_os.server``) keeps
  working untouched. Nothing in core imports this package at load time.
* Lazy heavy deps. The web/serving stack lives in the optional
  ``research-os[daemon]`` extra and is imported lazily inside the methods
  that need it, so ``import research_os.daemon`` stays cheap and never
  fails on a core-only install.

Phase 0: the skeleton — config, a ``Daemon`` holder, and a status report.
Phase 1 (current): the persistent core loop — a multi-root state registry,
a background task queue ("master loop owns execution"), and read-only HTTP
endpoints (``/healthz``, ``/v1/state``, ``/v1/jobs``). Later phases add the
OpenAI-compatible gateway, the MCP telemetry sidecar, the sandbox, and the
dashboard.
"""
from __future__ import annotations

from .artifacts import diff as artifacts_diff
from .artifacts import snapshot as artifacts_snapshot
from .config import DaemonConfig
from .core import Daemon, DaemonStatus
from .events import Event, EventBus
from .registry import Workspace, WorkspaceRegistry
from .reproduce import compare_artifacts
from .runners import RunResult, SubprocessRunner
from .runstore import RunJournal, RunStore, build_manifest
from .schedulers import SchedulerResult, SchedulerRunner, SlurmAdapter, get_adapter
from .tasks import Job, JobStatus, TaskQueue

__all__ = [
    "Daemon",
    "DaemonConfig",
    "DaemonStatus",
    "WorkspaceRegistry",
    "Workspace",
    "TaskQueue",
    "Job",
    "JobStatus",
    "EventBus",
    "Event",
    "SubprocessRunner",
    "RunResult",
    "RunStore",
    "RunJournal",
    "build_manifest",
    "artifacts_snapshot",
    "artifacts_diff",
    "compare_artifacts",
    "SchedulerRunner",
    "SchedulerResult",
    "SlurmAdapter",
    "get_adapter",
]
