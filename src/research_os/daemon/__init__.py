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

Phase 0 (this file): the skeleton — config, a ``Daemon`` holder, and a
status report. No serving yet. Later phases fill in the core loop, the
OpenAI-compatible gateway, the MCP telemetry sidecar, the sandbox, and
the dashboard.
"""
from __future__ import annotations

from .config import DaemonConfig
from .core import Daemon, DaemonStatus

__all__ = ["Daemon", "DaemonConfig", "DaemonStatus"]
