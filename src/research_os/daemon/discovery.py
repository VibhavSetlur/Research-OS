"""Daemon discovery handshake — the bridge between surfaces (Phase 3).

A running daemon and an MCP session (Claude Code / Cursor) are separate
processes. For the MCP surface to *see* a live daemon — its jobs, its
freshness verdict, its recommended next action — it needs a way to find
it. This module is that handshake.

On ``serve()``, the daemon atomically writes a tiny JSON descriptor to
``<root>/.os_state/daemon.json`` (host, port, pid, version, started_at,
base_url) and removes it on clean exit. Anyone who can read the project
directory can discover the daemon and talk to it over its already-public
read-only HTTP surface — no daemon import required.

CRITICAL SEAM NOTE: this module lives in the daemon package and is used
by the *writer* (the daemon). The *reader* on the reasoning side (the
``sys_daemon`` MCP tool) must NOT import this module — that would make the
reasoning layer import the daemon and break the preflight-enforced
invariant. The read shape is deliberately trivial (one JSON file, three
fields) so the reasoning side can re-implement the read with pure stdlib.
The on-disk schema is the contract; keep both sides in sync by SHAPE, not
by shared import. The schema version below is the coordination point.

Pure stdlib; no third-party imports; never raises on the happy path of a
missing/locked file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Bump when the on-disk shape changes; readers may check this.
DISCOVERY_SCHEMA = 1
DISCOVERY_FILENAME = "daemon.json"


def discovery_path(root: Path | str) -> Path:
    """Return the discovery-file path for a project root."""
    return Path(root) / ".os_state" / DISCOVERY_FILENAME


def write_discovery(
    root: Path | str,
    *,
    host: str,
    port: int,
    version: str,
    started_at: str,
) -> Path:
    """Atomically write the daemon descriptor. Returns the path written.

    Best-effort durability: writes to a temp sibling then ``os.replace``
    so a reader never sees a half-written file. Creates ``.os_state/`` if
    needed.
    """
    path = discovery_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": DISCOVERY_SCHEMA,
        "host": host,
        "port": int(port),
        "pid": os.getpid(),
        "version": version,
        "started_at": started_at,
        "base_url": f"http://{host}:{port}",
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def clear_discovery(root: Path | str) -> None:
    """Remove the discovery file. Never raises if it is already gone."""
    try:
        discovery_path(root).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def read_discovery(root: Path | str) -> dict | None:
    """Read the descriptor, or ``None`` if absent/unreadable.

    Mirrors the stdlib read the reasoning-side ``sys_daemon`` tool does;
    kept here for the daemon's own ``status`` use.
    """
    path = discovery_path(root)
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    """Best-effort liveness check for a PID (POSIX ``kill -0``)."""
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by another user — still alive.
        return True
    except (OSError, TypeError, ValueError):
        return False
    return True
