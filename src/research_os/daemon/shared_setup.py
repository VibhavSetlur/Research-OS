"""Shared-server daemon setup helpers (no Docker, conda, custom ports).

Argonne-style HPC login nodes: no Docker, no systemd, conda for everything,
multiple users + projects on one box. This module makes the daemon easy to
stand up there:

  * pick a FREE port (so two projects / two users don't collide on 8787);
  * detect the conda/venv so the MCP + launch use the ABSOLUTE interpreter path
    (the bare `research-os` command fails when spawned outside the env);
  * launch the daemon DETACHED via nohup (no systemd needed), logging to
    .os_state/daemon.log, with the pid recorded for `daemon stop`.

stdlib-only; reasoning/CLI-side (no server/tools hot-path constraints). Safe to
import without the [daemon] extra — it only shells out / inspects the env.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

DEFAULT_PORT = 8787


def find_free_port(host: str = "127.0.0.1", preferred: int = DEFAULT_PORT,
                   span: int = 100) -> int:
    """Return a free TCP port at/after ``preferred`` (so per-project daemons
    coexist on a shared node). Falls back to an OS-assigned port if the span is
    exhausted."""
    for port in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def research_os_executable() -> str:
    """Absolute path to the `research-os` entrypoint, env-resolved.

    On a shared node the IDE / a detached process may run outside the conda env,
    where the bare `research-os` isn't on PATH. Prefer the resolved absolute
    path; fall back to `<python> -m research_os` which always works in-env.
    """
    found = shutil.which("research-os")
    if found:
        return found
    return f"{sys.executable} -m research_os"


def conda_env_name() -> str | None:
    """The active conda env name, if any (for the setup report)."""
    return os.environ.get("CONDA_DEFAULT_ENV")


def background_launch_command(root: Path, port: int, host: str = "127.0.0.1") -> str:
    """The exact copy-paste nohup command to run the daemon detached.

    Uses the absolute executable so it survives a shell that hasn't activated
    the conda env, logs to .os_state/daemon.log, and backgrounds with nohup
    (no systemd required).
    """
    exe = research_os_executable()
    log = root / ".os_state" / "daemon.log"
    return (
        f"nohup {exe} daemon start --workspace {root} --host {host} "
        f"--port {port} > {log} 2>&1 &"
    )


def launch_background(root: Path, port: int, host: str = "127.0.0.1") -> dict:
    """Start the daemon detached (nohup-style) and return immediately.

    Returns {pid, port, host, log, command}. The child writes its own discovery
    descriptor (<root>/.os_state/daemon.json) on startup, so `daemon stop` finds
    it. Fail-safe: raises only if the process can't be spawned at all.
    """
    root = Path(root)
    log = root / ".os_state" / "daemon.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    exe = research_os_executable()
    # Build argv (handle the "<python> -m research_os" fallback form).
    argv = exe.split() + [
        "daemon", "start", "--workspace", str(root),
        "--host", host, "--port", str(port),
    ]
    logf = open(log, "ab")  # noqa: SIM115 - handed to the child, closed by it
    proc = subprocess.Popen(
        argv, stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach from the controlling terminal
        cwd=str(root),
    )
    return {
        "pid": proc.pid, "port": port, "host": host,
        "log": str(log), "command": background_launch_command(root, port, host),
    }
